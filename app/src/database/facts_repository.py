"""
MongoDB repository for the Daily Facts feature.

Handles deduplication, storage, and retrieval of generated facts.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import List, Optional

from pymongo.errors import DuplicateKeyError

from configs.config import get_config
from src.database.connection import get_db

logger = logging.getLogger(__name__)

cfg = get_config()


def _compute_content_hash(headline_fact: str) -> str:
    """Compute a SHA-256 hash of the headline for exact deduplication."""
    return hashlib.sha256(headline_fact.strip().lower().encode("utf-8")).hexdigest()


def _extract_topic_key(topic: str) -> str:
    """
    Extract a compact 2-word key from a topic string.

    Examples:
        'Indian Spice Production' -> 'Spice Production'
        'Chandrayaan Moon Mission' -> 'Moon Mission'
        'UPI' -> 'UPI'
    """
    return topic.strip()


def get_recent_topic_keys(category: str, limit: Optional[int] = None) -> List[str]:
    """
    Fetch recent short topic keys for a specific category.

    Used as a compact deduplication blocklist in the LLM prompt.
    Only returns topic_key values for the requested category.
    """
    if limit is None:
        limit = cfg.FACTS_DEDUP_LIMIT

    db = get_db()
    cursor = (
        db[cfg.DAILY_FACTS_COLLECTION]
        .find(
            {"category": category},
            {"topic_key": 1, "_id": 0},
        )
        .sort("created_at", -1)
        .limit(limit)
    )
    return [doc["topic_key"] for doc in cursor if "topic_key" in doc]


def store_fact(fact_response: dict, category: str, generation_metadata: Optional[dict] = None) -> Optional[str]:
    """
    Store a generated fact in MongoDB for deduplication and caching.

    Returns the content_hash on success, None if a duplicate was detected.
    """
    headline = fact_response.get("headline_fact", "")
    topic = fact_response.get("topic", "")
    content_hash = _compute_content_hash(headline)

    document = {
        "category": category,
        "topic": topic,
        "topic_key": _extract_topic_key(topic),
        "headline_fact": headline,
        "full_response": fact_response,
        "content_hash": content_hash,
        "created_at": datetime.now(timezone.utc),
        "generation_metadata": generation_metadata or {},
    }

    db = get_db()
    try:
        db[cfg.DAILY_FACTS_COLLECTION].insert_one(document)
        logger.info(
            "Stored fact for category '%s': %s", category, topic
        )
        return content_hash
    except DuplicateKeyError:
        logger.info(
            "Duplicate fact detected (hash=%s), skipping storage",
            content_hash[:12],
        )
        return None


def get_random_cached_fact(category: str, include_metadata: bool = False) -> Optional[dict]:
    """
    Retrieve a beginner/intermediate fact for emergency fallback.

    Uses MongoDB's $sample aggregation to pick a random document.
    """
    db = get_db()
    pipeline = [
        {"$match": {"category": category, "full_response.difficulty_level": {
            "$in": ["beginner", "intermediate", "Beginner", "Intermediate"]}}},
        {"$sample": {"size": 1}},
        {"$project": {"full_response": 1, "content_hash": 1, "images": 1, "image_status": 1, "image_started_at": 1, "generation_metadata": 1, "_id": 0}},
    ]
    results = list(db[cfg.DAILY_FACTS_COLLECTION].aggregate(pipeline))
    if results:
        return results[0] if include_metadata else results[0].get("full_response")
    return None


def get_facts_list(
    category: Optional[str] = None, limit: int = 20, skip: int = 0
) -> List[dict]:
    """
    Retrieve a paginated list of previously generated facts.
    Optionally filter by category.
    """
    db = get_db()
    query = {}
    if category:
        query["category"] = category

    cursor = (
        db[cfg.DAILY_FACTS_COLLECTION]
        .find(query, {"_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    
    # We want to return the full fact responses, but maybe with a timestamp.
    # The stored document has "full_response" inside it, let's extract it.
    results = []
    for doc in cursor:
        fact_data = doc.get("full_response", {})
        # Optionally attach the generation timestamp
        if "created_at" in doc:
            fact_data["generated_at"] = doc["created_at"].isoformat()
        
        # Attach the content_hash so the frontend can reference it (e.g., for deletion)
        if "content_hash" in doc:
            fact_data["content_hash"] = doc["content_hash"]
            
        # Attach the OCI PAR image URLs
        if "images" in doc:
            fact_data["images"] = doc["images"]
        if 'image_credits' in doc:
            fact_data['image_credits'] = doc['image_credits']
        if 'country_photo_galleries' in doc:
            fact_data['country_photo_galleries'] = doc['country_photo_galleries']
            
        results.append(fact_data)
        
    return results


def update_fact_images(content_hash: str, images: dict) -> bool:
    """
    Update a fact with its generated image URLs (cover, history, how_it_works).
    """
    db = get_db()
    result = db[cfg.DAILY_FACTS_COLLECTION].update_one(
        {"content_hash": content_hash},
        {"$set": {"images": images, "image_ready": True}}
    )
    return result.modified_count > 0


def delete_fact(content_hash: str) -> bool:
    """
    Delete a fact by its content_hash.
    """
    db = get_db()
    result = db[cfg.DAILY_FACTS_COLLECTION].delete_one({"content_hash": content_hash})
    return result.deleted_count > 0


def get_fact_by_hash(content_hash: str) -> Optional[dict]:
    """
    Fetch a fact by its content hash.
    """
    db = get_db()
    return db[cfg.DAILY_FACTS_COLLECTION].find_one({"content_hash": content_hash}, {"_id": 0})


def start_fact_images(content_hash: str, keys: list) -> None:
    """Persist image work before scheduling it, including retry attempts."""
    updates = {f"image_status.{key}": "processing" for key in keys}
    updates.update(image_started_at=datetime.now(timezone.utc), image_ready=False)
    get_db()[cfg.DAILY_FACTS_COLLECTION].update_one(
        {"content_hash": content_hash}, {"$set": updates})


def set_fact_image_state(content_hash: str, key: str, status: str, url=None, credit=None, gallery=None, clear=False) -> None:
    """Save each result separately so partial results are immediately visible."""
    updates = {f"image_status.{key}": status}
    if url:
        updates[f"images.{key}"] = url
    if credit:
        updates[f"image_credits.{key}"] = credit
    if gallery is not None:
        updates[f'country_photo_galleries.{key}'] = gallery
    change={"$set":updates}
    if clear:
        change['$unset']={f'images.{key}':'',f'image_credits.{key}':''}
    get_db()[cfg.DAILY_FACTS_COLLECTION].update_one(
        {"content_hash": content_hash}, change)


def claim_country_photo_enrichment(content_hash: str) -> bool:
    """One cached photo-only search per plan version, with recovery after a stale worker."""
    from datetime import timedelta
    now=datetime.now(timezone.utc)
    result=get_db()[cfg.DAILY_FACTS_COLLECTION].update_one({'content_hash':content_hash,'$or':[
        {'country_photo_enrichment.version':{'$ne':3}},
        {'country_photo_enrichment.status':{'$in':['processing','failed']},'country_photo_enrichment.started_at':{'$lt':now-timedelta(minutes=5)}}]},
        {'$set':{'country_photo_enrichment':{'version':3,'status':'processing','started_at':now}}})
    return result.modified_count==1

def finish_country_photo_enrichment(content_hash: str,status='completed') -> None:
    get_db()[cfg.DAILY_FACTS_COLLECTION].update_one({'content_hash':content_hash},{'$set':{
        'country_photo_enrichment.version':3,'country_photo_enrichment.status':status,
        'country_photo_enrichment.finished_at':datetime.now(timezone.utc)}})

def finish_fact_images(content_hash: str) -> None:
    """Update the legacy completion flag without overwriting concurrent results."""
    from src.facts.lifecycle import image_generation_state
    document = get_fact_by_hash(content_hash)
    if document:
        state = image_generation_state(document, cfg.FACT_IMAGE_TIMEOUT_SECONDS)
        get_db()[cfg.DAILY_FACTS_COLLECTION].update_one(
            {"content_hash": content_hash},
            {"$set": {"image_ready": state["status"] == "completed"}},
        )
