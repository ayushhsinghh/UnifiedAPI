"""
Background transcription worker.

Extracts audio from a video file and generates SRT subtitles
using faster-whisper.  Progress is reported back to MongoDB.
"""

import logging
import subprocess

from faster_whisper import WhisperModel

from configs.config import get_config
from src.database.job_repository import (
    get_job,
    update_job_completion,
    update_job_error,
    update_job_progress,
    update_job_status,
)
from src.transcription.models import JobStatus

logger = logging.getLogger(__name__)
cfg = get_config()

# ── Model cache ──────────────────────────────────────────────────────────
_model_cache: dict = {}


def get_model(model_name: str) -> WhisperModel:
    """Return a cached WhisperModel, loading it on first access."""
    if model_name not in _model_cache:
        logger.info("Loading WhisperModel '%s'…", model_name)
        _model_cache[model_name] = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
            cpu_threads=4,
            num_workers=2,
        )
        logger.info("WhisperModel '%s' loaded successfully", model_name)
    return _model_cache[model_name]


# ── Audio helpers ────────────────────────────────────────────────────────


def get_audio_duration(audio_path: str) -> float:
    """Return audio duration in seconds via ffprobe, or 0 on failure."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
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
        logger.warning(
            "Could not get audio duration: %s. Progress tracking limited.", exc
        )
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


def format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int(seconds % 3600 // 60)
    secs = seconds % 60
    return f"{hours:02}:{minutes:02}:{secs:06.3f}".replace(".", ",")


# ── Main worker ──────────────────────────────────────────────────────────


def transcribe_job(job_id: str) -> None:
    """
    End-to-end transcription pipeline for a single job.

    1. Extract audio from video
    2. Run Whisper transcription
    3. Write SRT file with live progress updates
    """
    job = get_job(job_id)
    if not job:
        logger.error("Job %s not found in database", job_id)
        return

    logger.info("Starting transcription for job %s", job_id)
    update_job_status(job_id, JobStatus.RUNNING)

    video_path = f"{cfg.UPLOAD_DIR}/{job['video']}"
    audio_path = f"{cfg.UPLOAD_DIR}/{job['audio']}"
    srt_path = f"{cfg.OUTPUT_DIR}/{job['srt']}"

    try:
        extract_audio(video_path, audio_path)

        audio_duration = get_audio_duration(audio_path)

        model_name = job.get("model", "base")
        logger.info(
            "Transcription config — model=%s, language=%s, translate=%s",
            model_name, job.get("language"), job.get("translate"),
        )

        model = get_model(model_name)
        segments, info = model.transcribe(
            audio_path,
            language=job.get("language"),
            task="translate" if job.get("translate") else "transcribe",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
        logger.info(
            "Transcription complete. Detected language: %s", info.language
        )

        segment_count = _write_srt(
            job_id, srt_path, segments, audio_duration
        )

        logger.debug("SRT written with %d segments", segment_count)
        update_job_completion(job_id, info.language)
        update_job_status(job_id, JobStatus.DONE)
        logger.info("Job %s completed successfully", job_id)

    except Exception as exc:
        logger.error(
            "Job %s failed: %s", job_id, exc, exc_info=True
        )
        update_job_error(job_id, str(exc))
        update_job_status(job_id, JobStatus.FAILED)


def _write_srt(
    job_id: str,
    srt_path: str,
    segments,
    audio_duration: float,
) -> int:
    """Stream Whisper segments into an SRT file, reporting progress."""
    segment_count = 0
    with open(srt_path, "w", encoding="utf-8") as srt_file:
        for seg in segments:
            segment_count += 1
            srt_file.write(f"{segment_count}\n")
            srt_file.write(
                f"{format_timestamp(seg.start)} --> "
                f"{format_timestamp(seg.end)}\n"
            )
            srt_file.write(seg.text.strip() + "\n\n")

            _report_progress(
                job_id, segment_count, seg.end, audio_duration
            )
    return segment_count


def _report_progress(
    job_id: str,
    segment_count: int,
    segment_end_time: float,
    audio_duration: float,
) -> None:
    """Send a progress update to the database."""
    if audio_duration > 0:
        progress = min(
            int((segment_end_time / audio_duration) * 100), 99
        )
    else:
        progress = segment_count  # fallback

    success = update_job_progress(job_id, segment_count, progress)
    if success:
        logger.debug(
            "Job %s progress: %d segments, %d%%",
            job_id, segment_count, progress,
        )
    else:
        logger.warning("Job %s failed to update progress", job_id)
