"""
Repository functions for transcription jobs.

Each function is a thin wrapper around a MongoDB operation,
keeping the database access pattern consistent and testable.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from configs.config import get_config
from src.database.connection import get_db

logger = logging.getLogger(__name__)

cfg = get_config()


# ── Create ───────────────────────────────────────────────────────────────


def create_job(job_id: str, user_email: str, job_data: Dict) -> Dict:
    """Insert a new transcription job document."""
    db = get_db()
    job_document = {
        "job_id": job_id,
        "user_email": user_email,
        "status": job_data["status"],
        "video": job_data["video"],
        "audio": job_data["audio"],
        "srt": job_data["srt"],
        "original_filename": job_data.get("original_filename", ""),
        "translate": job_data.get("translate", False),
        "language": job_data.get("language"),
        "model": job_data.get("model", "online"),
        "detected_language": None,
        "total_segments": 0,
        "completed_segments": 0,
        "progress_percentage": 0,
        "error": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    db[cfg.JOBS_COLLECTION].insert_one(job_document)
    logger.debug("Job %s created in MongoDB", job_id)
    return job_document


# ── Read ─────────────────────────────────────────────────────────────────


def get_job(job_id: str, user_email: Optional[str] = None) -> Optional[Dict]:
    """Retrieve a single job by its ID, optionally enforcing ownership."""
    try:
        db = get_db()
        query = {"job_id": job_id}
        if user_email:
            query["user_email"] = user_email
            
        job = db[cfg.JOBS_COLLECTION].find_one(query)
        if job:
            job.pop("_id", None)
            logger.debug("Job %s retrieved from MongoDB", job_id)
            return job
        logger.warning("Job %s not found in MongoDB", job_id)
        return None
    except Exception as exc:
        logger.error(
            "Error getting job %s from MongoDB: %s", job_id, exc, exc_info=True
        )
        return None


def get_all_jobs(user_email: str, status: Optional[str] = None) -> List[Dict]:
    """Return all jobs for a specific user, optionally filtered by status."""
    try:
        db = get_db()
        query = {"user_email": user_email}
        if status is not None:
            query["status"] = status
            
        jobs = list(
            db[cfg.JOBS_COLLECTION].find(query).sort("created_at", -1)
        )
        for job in jobs:
            job.pop("_id", None)
        logger.debug("Retrieved %d jobs with status=%s", len(jobs), status)
        return jobs
    except Exception as exc:
        logger.error("Error getting all jobs: %s", exc, exc_info=True)
        return []


# ── Update ───────────────────────────────────────────────────────────────


def update_job_status(job_id: str, status: str) -> bool:
    """Set the status field for a job."""
    try:
        db = get_db()
        result = db[cfg.JOBS_COLLECTION].update_one(
            {"job_id": job_id},
            {"$set": {"status": status, "updated_at": datetime.utcnow()}},
        )
        if result.modified_count > 0:
            logger.info("Job %s status updated to %s", job_id, status)
            return True
        logger.warning(
            "Job %s status update to %s failed — no match", job_id, status
        )
        return False
    except Exception as exc:
        logger.error(
            "Error updating job status for %s: %s", job_id, exc, exc_info=True
        )
        return False


def update_job_progress(
    job_id: str, completed_segments: int, progress_percentage: int
) -> bool:
    """Update segment-level progress for a running job."""
    progress_percentage = max(0, min(progress_percentage, 100))
    try:
        db = get_db()
        result = db[cfg.JOBS_COLLECTION].update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "completed_segments": completed_segments,
                    "progress_percentage": progress_percentage,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        if result.modified_count > 0:
            logger.debug(
                "Job %s progress: %d segments, %d%%",
                job_id, completed_segments, progress_percentage,
            )
        else:
            logger.warning("Job %s progress update failed — no match", job_id)
        return result.modified_count > 0
    except Exception as exc:
        logger.error(
            "Job %s progress update error: %s", job_id, exc, exc_info=True
        )
        return False


def update_job_total_segments(job_id: str, total_segments: int) -> bool:
    """Set the total number of segments/chunks for a running job."""
    try:
        db = get_db()
        result = db[cfg.JOBS_COLLECTION].update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "total_segments": total_segments,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        if result.modified_count > 0:
            logger.info(
                "Job %s total_segments set to %d", job_id, total_segments
            )
        else:
            logger.warning(
                "Job %s total_segments update failed — no match", job_id
            )
        return result.modified_count > 0
    except Exception as exc:
        logger.error(
            "Job %s total_segments update error: %s",
            job_id, exc, exc_info=True,
        )
        return False


def update_job_error(job_id: str, error: str) -> bool:
    """Mark a job as errored with a descriptive message."""
    try:
        db = get_db()
        result = db[cfg.JOBS_COLLECTION].update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "error": error,
                    "status": "error",
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        if result.modified_count > 0:
            logger.error("Job %s marked as error: %s", job_id, error)
            return True
        logger.warning("Job %s error update failed — no match", job_id)
        return False
    except Exception as exc:
        logger.error(
            "Error updating job error for %s: %s", job_id, exc, exc_info=True
        )
        return False


def update_job_completion(job_id: str, detected_language: str) -> bool:
    """Record the detected language after successful transcription."""
    try:
        db = get_db()
        result = db[cfg.JOBS_COLLECTION].update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "detected_language": detected_language,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        if result.modified_count > 0:
            logger.info(
                "Job %s completed with language %s", job_id, detected_language
            )
            return True
        logger.warning("Job %s completion update failed — no match", job_id)
        return False
    except Exception as exc:
        logger.error(
            "Error updating job completion for %s: %s",
            job_id, exc, exc_info=True,
        )
        return False


# ── Delete ───────────────────────────────────────────────────────────────


def delete_job(job_id: str, user_email: Optional[str] = None) -> bool:
    """Remove a job document from the database, optionally enforcing ownership."""
    try:
        db = get_db()
        query = {"job_id": job_id}
        if user_email:
            query["user_email"] = user_email
            
        result = db[cfg.JOBS_COLLECTION].delete_one(query)
        if result.deleted_count > 0:
            logger.info("Job %s deleted from MongoDB", job_id)
            return True
        logger.warning("Job %s delete failed — no match", job_id)
        return False
    except Exception as exc:
        logger.error("Error deleting job %s: %s", job_id, exc, exc_info=True)
        return False
