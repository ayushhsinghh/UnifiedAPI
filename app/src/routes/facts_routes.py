"""
Daily Learning Facts API routes.

Endpoints:
    GET /api/facts/random?category=food  — generate a random educational fact
    GET /api/facts/categories            — list supported categories
"""

import hmac
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from commons import limiter
from configs.config import get_config
from security import safe_error_response, validate_category
from src.database.fact_jobs_repository import (
    create_fact_job,
    get_fact_job,
    update_fact_job,
)
from src.database.facts_repository import (
    get_facts_list,
    get_random_cached_fact,
    get_recent_topic_keys,
    store_fact,
)
from src.facts.fact_generator import (
    SUPPORTED_CATEGORIES,
    generate_daily_fact,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["facts"])

cfg = get_config()


# ── Helpers ──────────────────────────────────────────────────────────────


def _has_valid_bypass_key(request: Request) -> bool:
    """
    Check if the request carries a valid X-Facts-Key header
    that bypasses the daily rate limit.

    Uses constant-time comparison to prevent timing attacks.
    """
    provided_key = request.headers.get("X-Facts-Key", "")
    if not provided_key:
        return False
    return hmac.compare_digest(provided_key, cfg.FACTS_API_KEY)


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/facts/categories")
@limiter.limit("30/minute")
async def list_categories(request: Request) -> dict:
    """List all supported fact categories with their descriptions."""
    from src.facts.fact_generator import CATEGORY_HINTS

    categories = []
    for key in sorted(CATEGORY_HINTS.keys()):
        categories.append({
            "id": key,
            "name": key.replace("_", " ").title(),
            "hints": CATEGORY_HINTS[key],
        })

    return {
        "success": True,
        "categories": categories,
        "total": len(categories),
    }


async def process_fact_generation_task(
    job_id: str, category: str, blocklist: list
) -> None:
    """Background task to generate a fact and update job state."""
    logger.info("Starting fact generation task for job %s", job_id)
    start_time = time.monotonic()
    
    try:
        fact = await generate_daily_fact(category, blocklist)
        if not fact:
            raise RuntimeError("Generator returned None (all retries failed)")
    except Exception as exc:
        logger.error("Fact generation failed for job %s: %s", job_id, exc)
        # Try fallback
        try:
            fact = get_random_cached_fact(category)
            if not fact:
                update_fact_job(job_id, "failed", error="Generation failed and no cached facts available.")
                return
            logger.info("Job %s using fallback cached fact", job_id)
        except Exception as cache_exc:
            update_fact_job(job_id, "failed", error=f"Generation failed: {exc}")
            return
    
    generation_time_ms = int((time.monotonic() - start_time) * 1000)
    
    # Pack meta info
    fact_response = {
        "success": True,
        "fact": fact,
        "meta": {
            "source": "gemini",
            "generation_time_ms": generation_time_ms,
            "category_requested": category,
        },
    }

    # Store for dedup & caching
    try:
        store_fact(fact, category)
    except Exception as exc:
        logger.warning("Failed to store fact for job %s: %s", job_id, exc)

    # Update job
    update_fact_job(job_id, "completed", fact_data=fact_response)
    logger.info("Task for job %s completed successfully", job_id)


@router.post("/facts/generate")
@limiter.limit("10/day")
async def generate_fact_job(
    request: Request,
    background_tasks: BackgroundTasks,
    category: str = Query(
        ...,
        min_length=1,
        max_length=50,
        description="Fact category (e.g., 'food', 'space', 'indian_politics')",
    ),
) -> dict:
    """
    Start an asynchronous job to generate a random, structured, educational fact.

    Rate limited to 10 requests/day per IP.
    Returns a job_id. Use GET /api/facts/status/{job_id} to poll for completion.
    """
    category = validate_category(category)

    # Fetch dedup blocklist (category-scoped)
    try:
        blocklist = get_recent_topic_keys(category)
    except Exception as exc:
        logger.warning("Failed to fetch blocklist: %s", exc)
        blocklist = []

    # Create job state
    job_id = str(uuid.uuid4())
    create_fact_job(job_id, category)

    # Queue background task
    background_tasks.add_task(process_fact_generation_task, job_id, category, blocklist)

    return {
        "success": True,
        "job_id": job_id,
        "status": "processing",
        "message": "Fact generation started. Poll /api/facts/status/{job_id} for completion."
    }


@router.get("/facts/status/{job_id}")
async def get_fact_job_status(job_id: str) -> dict:
    """
    Check the status of a fact generation job.
    Returns status: 'processing', 'completed', or 'failed'.
    If 'completed', it includes the fact_data payload.
    """
    job = get_fact_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "success": True,
        "job_id": job_id,
        "status": job["status"],
    }
    
    if job["status"] == "completed":
        response["data"] = job["fact_data"]
    elif job["status"] == "failed":
        response["error"] = job.get("error", "Unknown error")
        
    return response


@router.get("/facts/history")
async def get_facts_history(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(20, ge=1, le=100, description="Number of facts to return"),
    skip: int = Query(0, ge=0, description="Number of facts to skip (pagination)")
) -> dict:
    """
    Retrieve a list of all previously generated facts, sorted by newest first.
    Includes pagination (limit/skip) and optional category filtering.
    """
    if category:
        # Validate using our existing helper to ensure format is safe
        category = validate_category(category)
        
    facts = get_facts_list(category=category, limit=limit, skip=skip)
    
    return {
        "success": True,
        "count": len(facts),
        "limit": limit,
        "skip": skip,
        "category_filter": category,
        "facts": facts,
    }
