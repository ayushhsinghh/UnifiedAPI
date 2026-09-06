"""
Repository functions for fact generation jobs.
"""

import logging
from datetime import datetime
from typing import Dict, Optional

from configs.config import get_config
from src.database.connection import get_db

logger = logging.getLogger(__name__)
cfg = get_config()


def create_fact_job(job_id: str, category: str) -> Dict:
    """Insert a new fact generation job."""
    db = get_db()
    job_document = {
        "job_id": job_id,
        "category": category,
        "status": "processing",
        "fact_data": None,
        "error": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    db[cfg.FACT_JOBS_COLLECTION].insert_one(job_document)
    logger.debug("Fact job %s created in MongoDB", job_id)
    return job_document


def get_fact_job(job_id: str) -> Optional[Dict]:
    """Retrieve a fact generation job by its ID."""
    try:
        db = get_db()
        job = db[cfg.FACT_JOBS_COLLECTION].find_one({"job_id": job_id})
        if job:
            job.pop("_id", None)
            return job
        return None
    except Exception as exc:
        logger.error(
            "Error getting fact job %s from MongoDB: %s", job_id, exc, exc_info=True
        )
        return None


def update_fact_job(
    job_id: str, status: str, fact_data: Optional[Dict] = None, error: Optional[str] = None
) -> bool:
    """Update the status and result of a fact generation job."""
    try:
        db = get_db()
        update_fields = {
            "status": status,
            "updated_at": datetime.utcnow(),
        }
        if fact_data is not None:
            update_fields["fact_data"] = fact_data
        if error is not None:
            update_fields["error"] = error

        result = db[cfg.FACT_JOBS_COLLECTION].update_one(
            {"job_id": job_id},
            {"$set": update_fields},
        )
        if result.modified_count > 0:
            logger.debug("Fact job %s updated to status: %s", job_id, status)
            return True
        logger.warning("Fact job %s not found for update", job_id)
        return False
    except Exception as exc:
        logger.error("Error updating fact job %s: %s", job_id, exc, exc_info=True)
        return False
