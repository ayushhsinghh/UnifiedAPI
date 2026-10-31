"""
Transcription job API routes.

Endpoints:
    POST   /api/jobs                  — upload video & create job
    GET    /api/jobs/{job_id}         — poll job status
    GET    /api/jobs/{job_id}/subtitles — download SRT
    GET    /api/jobs                  — list all jobs
    DELETE /api/jobs/{job_id}         — delete a job
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
    Query,
    Depends,
)
from fastapi.responses import FileResponse, JSONResponse
from src.database import gemini_jobs_repository as gemini_repo
from src.routes.gemini_routes import artifact_response, owned, cancel_owned

from commons import generate_job_id, limiter
from configs.config import get_config
from security import validate_file_extension, validate_job_id, safe_error_response
from src.auth.tokens import get_current_user
from src.database.job_repository import create_job, delete_job, get_all_jobs, get_job
from src.transcription.models import JobStatus
from src.transcription.worker import transcribe_job

logger = logging.getLogger(__name__)

cfg = get_config()

router = APIRouter(prefix="/api", tags=["transcription"])


# ── Upload & Create ──────────────────────────────────────────────────────


@router.post("/jobs")
@limiter.limit("2/hour")
async def create_job_endpoint(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form(default=""),
    translate: str = Form(default="off"),
    model: str = Form(default="medium"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Upload a video file and queue a transcription job."""
    validate_file_extension(file.filename)

    job_id = generate_job_id()
    logger.info("Creating new job %s for file: %s", job_id, file.filename)

    video_filename = f"{job_id}_{file.filename}"
    audio_filename = f"{job_id}.wav"
    srt_filename = f"{job_id}.srt"

    video_path = f"{cfg.UPLOAD_DIR}/{video_filename}"
    audio_path = f"{cfg.UPLOAD_DIR}/{audio_filename}"
    srt_path = f"{cfg.OUTPUT_DIR}/{srt_filename}"

    translate_bool = translate.lower() in ("on", "true", "1", "yes")
    language_str = language if language else None

    if model in cfg.WHISPER_ALLOWED_MODELS:
        model_str = model
    else:
        model_str = cfg.WHISPER_DEFAULT_MODEL

    logger.info(
        "Job config — language: %s, translate: %s, model: %s",
        language_str, translate_bool, model_str,
    )

    try:
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
            "video": video_filename,
            "audio": audio_filename,
            "srt": srt_filename,
            "original_filename": file.filename,
            "translate": translate_bool,
            "language": language_str,
            "model": model_str,
        }

        user_email = current_user["email"]
        create_job(job_id, user_email, job_data)
        logger.debug("Job %s initialised in MongoDB (PENDING) for user %s", job_id, user_email)

        background_tasks.add_task(transcribe_job, job_id)
        logger.info("Background task queued for job %s", job_id)

        return {"job_id": job_id, "status": JobStatus.PENDING}

    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="create_job")


# ── Status ───────────────────────────────────────────────────────────────


@router.get("/jobs/{job_id}")
@limiter.limit("120/minute")
def get_status(request: Request, job_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    """Return current status and progress of a job."""
    validate_job_id(job_id)
    logger.debug("Status check for job %s", job_id)
    job = get_job(job_id, user_email=current_user["email"])
    if not job:
        logger.warning("Job %s not found for user %s", job_id, current_user["email"])
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("engine") == gemini_repo.ENGINE:
        return gemini_repo.public_job(job)

    return {
        "job_id": job_id,
        "status": job["status"],
        "progress_percentage": job.get("progress_percentage", 0),
        "completed_segments": job.get("completed_segments", 0),
        "total_segments": job.get("total_segments", 0),
        "language": job.get("language"),
        "detected_language": job.get("detected_language"),
        "translate": job.get("translate", False),
        "model": job.get("model", "base"),
    }


# ── Download ─────────────────────────────────────────────────────────────


@router.get("/jobs/{job_id}/subtitles")
@limiter.limit("30/minute")
def get_srt(request: Request, job_id: str, format: str = Query("srt", pattern="^(srt|vtt)$"), current_user: dict = Depends(get_current_user)) -> FileResponse:
    """Download the generated SRT subtitle file."""
    validate_job_id(job_id)
    job = get_job(job_id, user_email=current_user["email"])
    if job and job.get("engine") == gemini_repo.ENGINE:
        return artifact_response(job, format, request)
    if format != "srt":
        raise HTTPException(404, detail="VTT is available for Gemini jobs only.")
    if not job or job["status"] != JobStatus.DONE:
        raise HTTPException(status_code=404, detail="Subtitles not ready or job not found")

    logger.info("Subtitle file retrieved for job %s", job_id)
    srt_file_path = f"{cfg.OUTPUT_DIR}/{job['srt']}"
    return FileResponse(
        srt_file_path,
        media_type="application/x-subrip",
        filename="subtitles.srt",
    )


# ── List ─────────────────────────────────────────────────────────────────


@router.get("/jobs")
@limiter.limit("60/minute")
def list_jobs(request: Request, status: str | None = None, current_user: dict = Depends(get_current_user)) -> dict:
    """List all jobs for the currently authenticated user, optionally filtered by status."""
    logger.debug("Listing jobs with status filter: %s for user %s", status, current_user["email"])
    jobs_list = get_all_jobs(user_email=current_user["email"], status=status)
    return {"jobs": [gemini_repo.public_job(job) if job.get("engine") == gemini_repo.ENGINE else job
                     for job in jobs_list], "total": len(jobs_list)}


# ── Delete ───────────────────────────────────────────────────────────────


@router.delete("/jobs/{job_id}")
@limiter.limit("10/minute")
async def delete_job_endpoint(request: Request, job_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a job by ID, ensuring ownership."""
    validate_job_id(job_id)
    logger.info("Deleting job %s for user %s", job_id, current_user["email"])
    job = get_job(job_id, user_email=current_user["email"])
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("engine") == gemini_repo.ENGINE:
        result = await cancel_owned(job_id, current_user, delete=True)
        return JSONResponse(result, status_code=202 if result["status"] == "cancelling" else 200)
    try:
        success = delete_job(job_id, user_email=current_user["email"])
        if success:
            logger.info("Job %s deleted successfully", job_id)
            return {
                "message": f"Job {job_id} deleted successfully",
                "job_id": job_id,
            }
        raise HTTPException(status_code=500, detail="Failed to delete job")
    except HTTPException:
        raise
    except Exception as exc:
        safe_error_response(exc, context="delete_job")


@router.get("/jobs/{job_id}/audio")
@limiter.limit("120/minute")
def get_audio(request: Request, job_id: str, format: str = Query("wav", pattern="^(wav|mp3)$"),
              current_user: dict = Depends(get_current_user)):
    job = owned(job_id, current_user)
    if job.get('engine') != gemini_repo.ENGINE:
        raise HTTPException(404, 'Translated audio is unavailable for this job.')
    return artifact_response(job, format, request)


@router.post("/jobs/{job_id}/cancel", status_code=202)
@limiter.limit("10/minute")
async def cancel_job(request: Request, job_id: str, current_user: dict = Depends(get_current_user)):
    return await cancel_owned(job_id, current_user)


@router.post("/jobs/{job_id}/retry", status_code=202)
@limiter.limit("10/minute")
def retry_gemini_job(request: Request, job_id: str, current_user: dict = Depends(get_current_user)):
    from configs.config import get_config
    cfg = get_config()
    job = owned(job_id, current_user)
    if job.get('engine') != gemini_repo.ENGINE:
        raise HTTPException(409, 'Only Gemini translation jobs support this retry operation.')
    if not cfg.GEMINI_TRANSLATION_ENABLED or not cfg.GEMINI_API_KEY:
        raise HTTPException(503, 'Gemini audio translation is not enabled.')
    if not gemini_repo.retry(job_id, current_user['email']):
        raise HTTPException(409, 'Only failed or cancelled jobs can be retried.')
    logger.info('Gemini job_retry_queued job=%s completed_sections=%d', job_id, len(job.get('sections', [])))
    return {'job_id': job_id, 'status': 'pending'}
