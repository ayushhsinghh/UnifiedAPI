"""
Background worker for NVIDIA Riva ASR transcription.

Sends audio to the NVIDIA Riva cloud API and converts the response
into an SRT subtitle file.  Reports progress to MongoDB.
"""

import logging
import os
import shutil
import subprocess
import tempfile

import grpc
import riva.client

from src.database.job_repository import (
    get_job,
    update_job_completion,
    update_job_error,
    update_job_progress,
    update_job_status,
)
from src.transcription.models import JobStatus
from src.transcription.srt_utils import extract_srt_entries, write_combined_srt

logger = logging.getLogger(__name__)

# ── NVIDIA Riva config (from environment) ────────────────────────────────
NVIDIA_RIVA_SERVER = os.getenv("NVIDIA_RIVA_SERVER", "grpc.nvcf.nvidia.com:443")
NVIDIA_RIVA_FUNCTION_ID = os.getenv(
    "NVIDIA_RIVA_FUNCTION_ID", "b702f636-f60c-4a3d-a6f4-f3568c13bd7d"
)
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")

# gRPC message size — large enough for full audio files (500 MB)
MAX_GRPC_MESSAGE_LENGTH = 1024 * 1024 * 1024


# ── Audio helpers ────────────────────────────────────────────────────────


def get_audio_duration(audio_path: str) -> float:
    """Return audio duration in seconds via ffprobe, or 0 on failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        duration = float(result.stdout.strip())
        logger.info("Audio duration: %.2f seconds", duration)
        return duration
    except Exception as exc:
        logger.warning("Could not get audio duration: %s", exc)
        return 0.0


def extract_audio(video_path: str, audio_path: str) -> None:
    """Extract mono 16 kHz WAV audio from a video file."""
    logger.info("Extracting audio from %s to %s", video_path, audio_path)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", video_path,
                "-ac", "1",
                "-ar", "16000",
                "-threads", "4",
                audio_path,
            ],
            check=True,
            capture_output=True,
        )
        logger.info("Audio extraction completed successfully")
    except subprocess.CalledProcessError as exc:
        logger.error("Audio extraction failed: %s", exc, exc_info=True)
        raise


# ── Riva API ─────────────────────────────────────────────────────────────


def _build_riva_service():
    """Create and return a Riva ASR service client."""
    if not NVIDIA_API_KEY:
        raise ValueError(
            "NVIDIA_API_KEY environment variable is not set. "
            "Cannot connect to NVIDIA Riva API."
        )

    # metadata_args must be List[List[str]] per riva.client.Auth
    metadata = [
        ["function-id", NVIDIA_RIVA_FUNCTION_ID],
        ["authorization", f"Bearer {NVIDIA_API_KEY}"],
    ]

    # gRPC channel options — allow large audio payloads (up to 500 MB)
    options = [
        ("grpc.max_receive_message_length", MAX_GRPC_MESSAGE_LENGTH),
        ("grpc.max_send_message_length", MAX_GRPC_MESSAGE_LENGTH),
    ]

    auth = riva.client.Auth(
        use_ssl=True,
        uri=NVIDIA_RIVA_SERVER,
        metadata_args=metadata,
        options=options,
    )
    return riva.client.ASRService(auth)


def _build_riva_config(language: str = "en-US", translate: bool = False):
    """
    Build a Riva RecognitionConfig.

    Default values are aligned with the reference CLI script
    (python-clients/scripts/asr/transcribe_large_file_srt.py).
    """
    config = riva.client.RecognitionConfig(
        language_code=language,
        max_alternatives=1,
        profanity_filter=False,
        enable_automatic_punctuation=True,
        verbatim_transcripts=True,
        enable_word_time_offsets=True,
    )

    if translate:
        # add_custom_configuration_to_config expects a comma-separated
        # string of key:value pairs, e.g. "task:translate"
        riva.client.add_custom_configuration_to_config(
            config, "task:translate"
        )

    return config


# ── Main worker ──────────────────────────────────────────────────────────


def riva_transcribe_job(
    job_id: str,
    language: str = "ja",
    translate: bool = False,
) -> None:
    """
    End-to-end Riva transcription pipeline for a single job.

    1. Extract audio from video
    2. Send the full audio to NVIDIA Riva for transcription
    3. Write SRT file from the response
    """
    job = get_job(job_id)
    if not job:
        logger.error("Job %s not found in database", job_id)
        return

    logger.info("Starting Riva transcription for job %s", job_id)
    update_job_status(job_id, JobStatus.RUNNING)

    try:
        # Step 1: Extract audio
        extract_audio(job["video"], job["audio"])
        audio_duration = get_audio_duration(job["audio"])
        file_size_mb = os.path.getsize(job["audio"]) / (1024 * 1024)
        logger.info(
            "Riva job %s — audio: %.1fs (%.1f min), %.1f MB",
            job_id, audio_duration, audio_duration / 60, file_size_mb,
        )

        # Step 2: Build Riva client and config
        asr_service = _build_riva_service()
        config = _build_riva_config(
            language=language or "en-US",
            translate=translate,
        )
        # Set sample_rate_hertz and audio_channel_count from the actual WAV file
        riva.client.add_audio_file_specs_to_config(config, job["audio"])

        # Step 3: Send full audio to Riva
        update_job_progress(job_id, 0, 10)
        logger.info("Job %s — Sending %.1f MB to Riva...", job_id, file_size_mb)

        with open(job["audio"], "rb") as fh:
            audio_data = fh.read()

        response = asr_service.offline_recognize(audio_data, config)
        # logger.info("Job %s — Riva response: %s", job_id, response)

        update_job_progress(job_id, 1, 80)
        logger.info(
            "Job %s — Riva returned %d results",
            job_id, len(response.results),
        )

        # Build transcript preview for logging
        transcript_preview = ""
        for res in response.results:
            if len(res.alternatives) > 0:
                transcript_preview += res.alternatives[0].transcript
        if len(transcript_preview) > 200:
            transcript_preview = transcript_preview[:200] + "..."
        if transcript_preview:
            logger.info("Job %s — Preview: %s", job_id, transcript_preview)

        # Step 4: Convert to SRT
        entries = extract_srt_entries(response, time_offset_seconds=0.0)

        if len(entries) > 0:
            write_combined_srt(entries, job["srt"])
            logger.info(
                "Job %s — SRT written: %d entries",
                job_id, len(entries),
            )
        else:
            logger.warning("Job %s — No subtitles generated", job_id)

        update_job_progress(job_id, 1, 100)
        update_job_completion(job_id, language or "unknown")
        update_job_status(job_id, JobStatus.DONE)
        logger.info("Job %s completed successfully (Riva)", job_id)

    except grpc.RpcError as e:
        logger.error("Job %s — gRPC error: %s", job_id, e.details())
        update_job_error(job_id, f"Riva gRPC error: {e.details()}")
        update_job_status(job_id, JobStatus.FAILED)

    except Exception as exc:
        logger.error("Job %s failed: %s", job_id, exc, exc_info=True)
        update_job_error(job_id, str(exc))
        update_job_status(job_id, JobStatus.FAILED)
