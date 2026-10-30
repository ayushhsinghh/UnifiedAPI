"""
Daily Learning Facts API routes.

Endpoints:
    GET /api/facts/random?category=food  — generate a random educational fact
    GET /api/facts/categories            — list supported categories
"""

import asyncio
import hmac
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request, Depends
from fastapi.responses import JSONResponse

from commons import limiter
from configs.config import get_config
from security import safe_error_response, validate_category, require_facts_api_key
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
    delete_fact,
    get_fact_by_hash,
    _compute_content_hash,
    start_fact_images,
    set_fact_image_state,
    finish_fact_images,
)
from src.facts.fact_generator import (
    SUPPORTED_CATEGORIES,
    generate_daily_fact,
)
from src.facts.lifecycle import expected_image_keys, image_generation_state
from src.facts.visual_prompts import IMAGE_SECTION_BRIEFS, build_section_image_context
from src.facts.image_generator import generate_and_save_image

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
            "name": key.replace("_", " ").title()
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
    
    generation_metadata = {}
    cached = None
    try:
        fact = await asyncio.wait_for(
            generate_daily_fact(category, blocklist, generation_metadata=generation_metadata),
            timeout=cfg.FACT_JOB_TIMEOUT_SECONDS - 5,
        )
        if not fact:
            raise RuntimeError("All generation attempts failed")
    except Exception:
        logger.exception("Fact generation failed for job %s", job_id)
        try:
            cached = get_random_cached_fact(category, include_metadata=True)
            if not cached or not cached.get("full_response"):
                update_fact_job(job_id, "failed", error="Generation failed and no cached facts available.")
                return
            fact = dict(cached["full_response"])
            fact["images"] = cached.get("images") or fact.get("images") or {}
            generation_metadata = cached.get("generation_metadata") or {}
        except Exception:
            logger.exception("Cached fallback failed for job %s", job_id)
            update_fact_job(job_id, "failed", error="Generation failed and cached facts are unavailable.")
            return

    content_hash = cached.get("content_hash") if cached else None
    stored = cached
    if not cached:
        try:
            content_hash = store_fact(fact, category, generation_metadata=generation_metadata)
            if content_hash:
                keys = expected_image_keys(fact.get("visual_suggestions"))
                if keys:
                    start_fact_images(content_hash, keys)
                    asyncio.create_task(_background_image_task(fact["visual_suggestions"], content_hash, article=fact))
            else:
                # Exact duplicates still reference their existing images and state.
                content_hash = _compute_content_hash(fact["headline_fact"])
            stored = get_fact_by_hash(content_hash)
        except Exception:
            logger.exception("Failed to store fact for job %s", job_id)
    if stored and stored.get("images"):
        fact["images"] = stored["images"]
    image_state = image_generation_state(stored or {"full_response": fact}, cfg.FACT_IMAGE_TIMEOUT_SECONDS)
    fact_response = {
        "success": True,
        "fact": fact,
        "content_hash": content_hash,
        "image_generation": image_state,
        "meta": {
            "source": "cache" if cached else generation_metadata.get("provider", "unknown"),
            "provider": generation_metadata.get("provider"),
            "model": generation_metadata.get("model"),
            "cached": cached is not None,
            "generation_time_ms": int((time.monotonic() - start_time) * 1000),
            "category_requested": category,
        },
    }
    if not update_fact_job(job_id, "completed", fact_data=fact_response):
        logger.error("Job %s could not be marked completed", job_id)


async def _background_image_task(visual_suggestions: dict, content_hash: str, existing_images: dict = None, article: dict = None):
    if existing_images is None:
        existing_images = {}
    images = existing_images.copy()
    
    async def process_image(key: str, filename: str, prompt: str, aspect_ratio: str, context: str):
        if key in existing_images:
            return
        try:
            url = await asyncio.wait_for(
                generate_and_save_image(prompt, filename, aspect_ratio=aspect_ratio, extra_context=context),
                timeout=cfg.FACT_IMAGE_TIMEOUT_SECONDS,
            )
            if url:
                images[key] = url
            set_fact_image_state(content_hash, key, "ready" if url else "failed", url)
        except Exception:
            logger.exception("Image generation failed for %s/%s", content_hash, key)
            set_fact_image_state(content_hash, key, "failed")

    tasks = []
    for key, brief in IMAGE_SECTION_BRIEFS.items():
        prompt = visual_suggestions.get(key)
        if key == "overview":
            prompt = prompt or visual_suggestions.get("history")
        if prompt:
            tasks.append(process_image(
                key, f"{content_hash}_{key}.jpg", prompt, brief["ratio"],
                build_section_image_context(key, article),
            ))

    if tasks:
        await asyncio.gather(*tasks)

    finish_fact_images(content_hash)
    logger.info("Background image generation finished for %s with %d images", content_hash, len(images))



@router.post("/facts/generate", dependencies=[Depends(require_facts_api_key)])
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
        "timeout_seconds": cfg.FACT_JOB_TIMEOUT_SECONDS,
        "poll_after_seconds": 4,
        "message": "Fact generation started. Poll /api/facts/status/{job_id} for completion."
    }


@router.get("/facts/status/{job_id}")
async def get_fact_job_status(job_id: str) -> dict:
    """
    Check the status of a fact generation job.
    Returns status: 'processing', 'completed', or 'failed'.
    If 'completed', it includes the fact_data payload.
    Images are generated asynchronously, so we merge them from the
    facts collection on every poll until they arrive.
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
        fact_data = job["fact_data"]
        # Merge images from the facts collection (they arrive after job completes)
        content_hash = fact_data.get("content_hash") if fact_data else None
        if content_hash:
            stored = get_fact_by_hash(content_hash)
            if stored:
                fact_data["fact"]["images"] = stored.get("images") or {}
                fact_data["image_generation"] = image_generation_state(stored, cfg.FACT_IMAGE_TIMEOUT_SECONDS)
        response["data"] = fact_data
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

@router.delete("/facts/{content_hash}")
async def delete_fact_endpoint(content_hash: str, x_admin_key: str = Header(None)) -> dict:
    """
    Delete a specific fact by its content hash.
    Requires X-Admin-Key header matching the config.
    """
    cfg = get_config()
    if not x_admin_key or x_admin_key != cfg.ADMIN_KEY:
        raise HTTPException(status_code=500, detail="Internal Server Error")

    success = delete_fact(content_hash)
    if not success:
        raise HTTPException(status_code=404, detail="Fact not found")
    return {"status": "success", "message": "Fact deleted"}

@router.post("/facts/{content_hash}/retry-images")
@limiter.limit("10/day")
async def retry_image_generation(
    request: Request,
    background_tasks: BackgroundTasks,
    content_hash: str
) -> dict:
    """
    Retry image generation for a fact, but only if the previous default run failed
    or did not generate all expected images.
    """
    fact_doc = get_fact_by_hash(content_hash)
    if not fact_doc:
        raise HTTPException(status_code=404, detail="Fact not found")
        
    full_response = fact_doc.get("full_response", {})
    visual_suggestions = full_response.get("visual_suggestions", {})
    if not visual_suggestions:
        raise HTTPException(status_code=400, detail="No visual suggestions available for this fact")
        
    existing_images = fact_doc.get("images", {})
    
    expected_keys = expected_image_keys(visual_suggestions)
        
    # Check if we have all expected keys
    missing_keys = [k for k in expected_keys if k not in existing_images]
    
    if not missing_keys:
        raise HTTPException(status_code=400, detail="Previous run was successful. All expected images are already generated.")
        
    logger.info("Retrying image generation for %s. Missing keys: %s", content_hash, missing_keys)
    start_fact_images(content_hash, missing_keys)
    background_tasks.add_task(_background_image_task, visual_suggestions, content_hash, existing_images, article=full_response)
    
    return {
        "success": True,
        "message": f"Retrying background image generation for missing keys: {missing_keys}"
    }
