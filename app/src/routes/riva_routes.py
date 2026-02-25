"""
NVIDIA Riva transcription job API routes.

Endpoints:
    POST /api/riva/jobs  — upload video & create a Riva transcription job

Status, download, list, and delete reuse the existing /api/jobs endpoints
since all jobs share the same MongoDB collection.
"""

import logging
import os

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    Depends,
)

from commons import generate_job_id, limiter
from configs.config import get_config
from security import validate_file_extension
from src.auth.tokens import get_current_user
from src.database.job_repository import create_job
from src.transcription.models import JobStatus
from src.transcription.riva_worker import riva_transcribe_job

logger = logging.getLogger(__name__)

cfg = get_config()

router = APIRouter(prefix="/api/riva", tags=["riva-transcription"])


# ── Upload & Create (Riva) ───────────────────────────────────────────────


@router.post("/jobs")
@limiter.limit("5/hour")
async def create_riva_job_endpoint(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form(default="ja"),
    translate: str = Form(default="on"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Upload a video/audio file and queue transcription via NVIDIA Riva.

    Supports files of any size — the worker automatically chunks large
    audio with ffmpeg before sending to the Riva API.

    Args:
        file: The video or audio file to transcribe.
        language: Source language code (default: ja-JP).
        translate: Whether to translate to English ("on"/"off").
    """
    validate_file_extension(file.filename)

    job_id = generate_job_id()
    logger.info(
        "Creating Riva job %s for file: %s (user: %s)",
        job_id, file.filename, current_user["email"],
    )

    video_path = f"{cfg.UPLOAD_DIR}/{job_id}_{file.filename}"
    audio_path = f"{cfg.UPLOAD_DIR}/{job_id}.wav"
    srt_path = f"{cfg.OUTPUT_DIR}/{job_id}.srt"

    translate_bool = translate.lower() in ("on", "true", "1", "yes")
    # language_str = language if language else "ja-JP"
    language_str = "ja"

    logger.info(
        "Riva job config — language: %s, translate: %s",
        language_str, translate_bool,
    )

    try:
        # Stream file to disk with size check
        total_bytes = 0
        with open(video_path, "wb") as video_file:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > cfg.MAX_UPLOAD_SIZE:
                    video_file.close()
                    os.remove(video_path)
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"File too large. Maximum allowed size is "
                            f"{cfg.MAX_UPLOAD_SIZE // (1024 ** 3)} GB."
                        ),
                    )
                video_file.write(chunk)

        logger.debug("File saved to %s (%d bytes)", video_path, total_bytes)

        job_data = {
            "status": JobStatus.PENDING,
            "video": video_path,
            "audio": audio_path,
            "srt": srt_path,
            "original_filename": file.filename,
            "translate": translate_bool,
            "language": language_str,
            "model": "riva",
        }

        user_email = current_user["email"]
        create_job(job_id, user_email, job_data)
        logger.debug("Job %s initialised in MongoDB (PENDING)", job_id)

        background_tasks.add_task(
            riva_transcribe_job,
            job_id,
            language=language_str,
            translate=translate_bool,
        )
        logger.info("Background Riva task queued for job %s", job_id)

        return {"job_id": job_id, "status": JobStatus.PENDING}

    except HTTPException:
        raise
    except Exception as exc:
        from security import safe_error_response
        safe_error_response(exc, context="create_riva_job")
