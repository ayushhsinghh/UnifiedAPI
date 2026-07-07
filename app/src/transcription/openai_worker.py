"""
Background worker for OpenAI Whisper-1 transcription and translation.

Sends audio to the OpenAI API and converts the response
into an SRT subtitle file. Reports progress to MongoDB.
"""

import logging
import math
import os
import re
import subprocess
import tempfile

from openai import OpenAI
from pydub import AudioSegment

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

# Maximum chunk duration in milliseconds (10 minutes).
# Whisper-1 accepts files up to 25 MB; 10-min mono WAV chunks stay well
# under that limit even at 44.1 kHz / 16-bit.
CHUNK_DURATION_MS = 10 * 60 * 1000  # 10 minutes

cfg = get_config()

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

# ── SRT helpers ──────────────────────────────────────────────────────────

def parse_srt_timestamp(ts: str) -> float:
    """Convert an SRT timestamp (HH:MM:SS,mmm) to seconds."""
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def format_srt_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def offset_srt(srt_text: str, offset_seconds: float, start_index: int) -> tuple[str, int]:
    """
    Shift all timestamps in *srt_text* by *offset_seconds* and
    re-number the cues starting from *start_index*.

    Returns (adjusted_srt_string, next_index).
    """
    timestamp_pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})"
    )

    lines = srt_text.strip().splitlines()
    result_lines: list[str] = []
    idx = start_index

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip blank lines between cues
        if not line:
            i += 1
            continue

        # Expect a cue index (digit line) – replace with our running index
        if line.isdigit():
            result_lines.append(str(idx))
            i += 1
            if i >= len(lines):
                break

            # Next line should be the timestamp line
            ts_line = lines[i].strip()
            match = timestamp_pattern.match(ts_line)
            if match:
                start = parse_srt_timestamp(match.group(1)) + offset_seconds
                end = parse_srt_timestamp(match.group(2)) + offset_seconds
                result_lines.append(
                    f"{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}"
                )
            else:
                result_lines.append(ts_line)
            i += 1

            # Collect subtitle text lines until blank line or next cue
            while i < len(lines) and lines[i].strip():
                result_lines.append(lines[i].strip())
                i += 1

            result_lines.append("")  # blank separator
            idx += 1
        else:
            i += 1

    return "\n".join(result_lines), idx

# ── Main worker ──────────────────────────────────────────────────────────

def openai_transcribe_job(
    job_id: str,
    language: str = "ja",
    translate: bool = True,
) -> None:
    """
    End-to-end OpenAI transcription pipeline for a single job.

    1. Extract audio from video
    2. Split audio into 10-minute chunks
    3. Send each chunk to OpenAI for translation
    4. Write combined SRT file with adjusted timestamps
    """
    job = get_job(job_id)
    if not job:
        logger.error("Job %s not found in database", job_id)
        return

    video_path = f"{cfg.UPLOAD_DIR}/{job['video']}"
    audio_path = f"{cfg.UPLOAD_DIR}/{job['audio']}"
    srt_path = f"{cfg.OUTPUT_DIR}/{job['srt']}"

    logger.info("Starting OpenAI transcription for job %s", job_id)
    update_job_status(job_id, JobStatus.RUNNING)

    try:
        if not os.getenv("OPENAI_API_KEY"):
             raise ValueError("OPENAI_API_KEY environment variable is not set")
             
        client = OpenAI()
        
        # Step 1: Extract audio
        extract_audio(video_path, audio_path)
        audio_duration = get_audio_duration(audio_path)
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        logger.info(
            "OpenAI job %s — audio: %.1fs (%.1f min), %.1f MB",
            job_id, audio_duration, audio_duration / 60, file_size_mb,
        )
        
        update_job_progress(job_id, 0, 10)

        # Step 2: Split audio
        logger.info("Loading audio with pydub: %s", audio_path)
        audio = AudioSegment.from_wav(audio_path)
        total_duration_ms = len(audio)
        num_chunks = math.ceil(total_duration_ms / CHUNK_DURATION_MS)

        logger.info("OpenAI job %s — Number of chunks: %d", job_id, num_chunks)

        all_srt_parts: list[str] = []
        cue_index = 1
        
        update_job_progress(job_id, 0, 15)

        with tempfile.TemporaryDirectory() as tmp_dir:
            for chunk_num in range(num_chunks):
                start_ms = chunk_num * CHUNK_DURATION_MS
                end_ms = min(start_ms + CHUNK_DURATION_MS, total_duration_ms)
                chunk = audio[start_ms:end_ms]

                # Export chunk as mono WAV to keep file size small
                chunk_path = os.path.join(tmp_dir, f"chunk_{chunk_num:03d}.wav")
                chunk.export(chunk_path, format="wav", parameters=["-ac", "1"])
                chunk_size_mb = os.path.getsize(chunk_path) / (1024 * 1024)

                logger.info(
                    "Job %s — Chunk %d/%d (%.1fs - %.1fs), %.1f MB",
                    job_id, chunk_num + 1, num_chunks, start_ms / 1000, end_ms / 1000, chunk_size_mb
                )

                # Step 3: Call OpenAI API
                with open(chunk_path, "rb") as audio_file:
                    if translate:
                         logger.info("Job %s - Translating chunk %d with whisper-1", job_id, chunk_num + 1)
                         response = client.audio.translations.create(
                             model="whisper-1",
                             file=audio_file,
                             response_format="srt",
                         )
                    else:
                         logger.info("Job %s - Transcribing chunk %d with whisper-1", job_id, chunk_num + 1)
                         response = client.audio.transcriptions.create(
                             model="whisper-1",
                             language=language,
                             file=audio_file,
                             response_format="srt",
                         )
                         
                if not response or not response.strip():
                    logger.info("Job %s - (no speech detected in chunk %d)", job_id, chunk_num + 1)
                else:
                    # Shift timestamps by the chunk's absolute offset
                    offset_seconds = start_ms / 1000
                    adjusted_srt, cue_index = offset_srt(
                        response, offset_seconds, cue_index
                    )
                    all_srt_parts.append(adjusted_srt)
                    
                # Update progress
                progress_pct = 15 + int(((chunk_num + 1) / num_chunks) * 80)
                update_job_progress(job_id, chunk_num + 1, progress_pct)

        # Step 4: Write final SRT
        if all_srt_parts:
             final_srt = "\n".join(all_srt_parts).strip() + "\n"
             with open(srt_path, "w", encoding="utf-8") as f:
                 f.write(final_srt)
             logger.info("Job %s — SRT written to %s", job_id, srt_path)
        else:
             logger.warning("Job %s — No subtitles generated", job_id)

        update_job_progress(job_id, num_chunks, 100)
        update_job_completion(job_id, language or "unknown")
        update_job_status(job_id, JobStatus.DONE)
        logger.info("Job %s completed successfully (OpenAI)", job_id)

    except Exception as exc:
        logger.error("Job %s failed: %s", job_id, exc, exc_info=True)
        update_job_error(job_id, str(exc))
        update_job_status(job_id, JobStatus.FAILED)
