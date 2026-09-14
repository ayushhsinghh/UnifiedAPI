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
    update_fact_images,
    delete_fact,
    get_fact_by_hash,
)
from src.facts.fact_generator import (
    SUPPORTED_CATEGORIES,
    generate_daily_fact,
)
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
    content_hash = None
    try:
        content_hash = store_fact(fact, category)
        if content_hash and fact.get("visual_suggestions"):
            logger.info("Visual suggestions found, dispatching background image generation for hash %s", content_hash)
            asyncio.create_task(_background_image_task(fact["visual_suggestions"], content_hash))
    except Exception as exc:
        logger.warning("Failed to store fact for job %s: %s", job_id, exc)

    # Update job — include content_hash so the status endpoint can look up images later
    fact_response["content_hash"] = content_hash
    update_fact_job(job_id, "completed", fact_data=fact_response)
    logger.info("Task for job %s completed successfully", job_id)

async def _background_image_task(visual_suggestions: dict, content_hash: str, existing_images: dict = None):
    if existing_images is None:
        existing_images = {}
    images = existing_images.copy()
    
    async def process_image(key: str, filename: str, prompt: str, aspect_ratio: str, context: str):
        if key in existing_images:
            return
        url = await generate_and_save_image(prompt, filename, aspect_ratio=aspect_ratio, extra_context=context)
        if url:
            images[key] = url

    tasks = []
    
    # 1. Cover (shared by both fact and mythbuster)
    if cover_prompt := visual_suggestions.get("cover"):
        tasks.append(process_image(
            "cover", f"{content_hash}_cover.jpg", cover_prompt, "16:9",
            "This image will be used as the main cover background at the top of the UI. It must leave a little negative left space for a headline overlay and MUST NOT contain any text, but make sure the negative left space is not full gradient colours."
        ))

    # 2. Overview (standard fact) — fallback to history for older structures
    if overview_prompt := visual_suggestions.get("overview") or visual_suggestions.get("history"):
        tasks.append(process_image(
            "overview", f"{content_hash}_overview.jpg", overview_prompt, "4:3",
            "This image is placed directly beneath 'The short version' summary of the topic in the UI. It should visually summarize the core idea."
        ))
            
    # 3. How it works (standard fact)
    if how_it_works_prompt := visual_suggestions.get("how_it_works"):
        tasks.append(process_image(
            "how_it_works", f"{content_hash}_how_it_works.jpg", how_it_works_prompt, "4:3",
            "This image is placed inline in the 'How it works' section of the UI. It should visually illustrate the mechanics, processes, or technicalities. IN THE IMAGE, MAKE SURE THE SPELLING OF WORDS IS ABSOLUTELY CORRECT"
        ))

    # 4. Myth visual (mythbuster only)
    if myth_visual_prompt := visual_suggestions.get("myth_visual"):
        tasks.append(process_image(
            "myth_visual", f"{content_hash}_myth_visual.jpg", myth_visual_prompt, "4:3",
            "This image depicts the myth AS IF IT WERE TRUE — the dramatic, exaggerated version people imagine. It is shown in the 'The Myth' section of a myth-busting article."
        ))

    # 5. Truth visual (mythbuster only)
    if truth_visual_prompt := visual_suggestions.get("truth_visual"):
        tasks.append(process_image(
            "truth_visual", f"{content_hash}_truth_visual.jpg", truth_visual_prompt, "4:3",
            "This image depicts the scientific reality — what actually happens. It is shown in the 'The Truth' section of a myth-busting article, alongside the debunking explanation."
        ))

    if tasks:
        await asyncio.gather(*tasks)

    if images:
        update_fact_images(content_hash, images)
        logger.info("Background image generation complete, DB updated for %s with %d images", content_hash, len(images))



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
        if content_hash and (not fact_data.get("fact", {}).get("images")):
            stored = get_fact_by_hash(content_hash)
            if stored and stored.get("images"):
                if "fact" not in fact_data:
                    fact_data["fact"] = {}
                fact_data["fact"]["images"] = stored["images"]
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
    
    # Calculate expected images
    expected_keys = []
    if visual_suggestions.get("cover"): 
        expected_keys.append("cover")
    if visual_suggestions.get("overview") or visual_suggestions.get("history"): 
        expected_keys.append("overview")
    if visual_suggestions.get("how_it_works"): 
        expected_keys.append("how_it_works")
    if visual_suggestions.get("myth_visual"):
        expected_keys.append("myth_visual")
    if visual_suggestions.get("truth_visual"):
        expected_keys.append("truth_visual")
        
    # Check if we have all expected keys
    missing_keys = [k for k in expected_keys if k not in existing_images]
    
    if not missing_keys:
        raise HTTPException(status_code=400, detail="Previous run was successful. All expected images are already generated.")
        
    logger.info("Retrying image generation for %s. Missing keys: %s", content_hash, missing_keys)
    background_tasks.add_task(_background_image_task, visual_suggestions, content_hash, existing_images)
    
    return {
        "success": True,
        "message": f"Retrying background image generation for missing keys: {missing_keys}"
    }
