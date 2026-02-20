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


def create_job(job_id: str, job_data: Dict) -> Dict:
    """Insert a new transcription job document."""
    db = get_db()
    job_document = {
        "job_id": job_id,
        "status": job_data["status"],
        "video": job_data["video"],
        "audio": job_data["audio"],
        "srt": job_data["srt"],
        "translate": job_data.get("translate", False),
        "language": job_data.get("language"),
        "model": job_data.get("model", "medium"),
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


def get_job(job_id: str) -> Optional[Dict]:
    """Retrieve a single job by its ID."""
    try:
        db = get_db()
        job = db[cfg.JOBS_COLLECTION].find_one({"job_id": job_id})
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


def get_all_jobs(status: Optional[str] = None) -> List[Dict]:
    """Return all jobs, optionally filtered by status."""
    try:
        db = get_db()
        query = {} if status is None else {"status": status}
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


def delete_job(job_id: str) -> bool:
    """Remove a job document from the database."""
    try:
        db = get_db()
        result = db[cfg.JOBS_COLLECTION].delete_one({"job_id": job_id})
        if result.deleted_count > 0:
            logger.info("Job %s deleted from MongoDB", job_id)
            return True
        logger.warning("Job %s delete failed — no match", job_id)
        return False
    except Exception as exc:
        logger.error("Error deleting job %s: %s", job_id, exc, exc_info=True)
        return False
