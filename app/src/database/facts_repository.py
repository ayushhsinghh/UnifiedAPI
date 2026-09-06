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
    words = topic.strip().split()
    if len(words) <= 2:
        return topic.strip()
    # Drop leading generic adjective (e.g., 'Indian') and take last 2 words
    return " ".join(words[-2:])


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


def store_fact(fact_response: dict, category: str) -> bool:
    """
    Store a generated fact in MongoDB for deduplication and caching.

    Returns True on success, False if a duplicate was detected.
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
    }

    db = get_db()
    try:
        db[cfg.DAILY_FACTS_COLLECTION].insert_one(document)
        logger.info(
            "Stored fact for category '%s': %s", category, topic
        )
        return True
    except DuplicateKeyError:
        logger.info(
            "Duplicate fact detected (hash=%s), skipping storage",
            content_hash[:12],
        )
        return False


def get_random_cached_fact(category: str) -> Optional[dict]:
    """
    Retrieve a random previously-generated fact for emergency fallback.

    Uses MongoDB's $sample aggregation to pick a random document.
    """
    db = get_db()
    pipeline = [
        {"$match": {"category": category}},
        {"$sample": {"size": 1}},
        {"$project": {"full_response": 1, "_id": 0}},
    ]
    results = list(db[cfg.DAILY_FACTS_COLLECTION].aggregate(pipeline))
    if results:
        return results[0].get("full_response")
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
        results.append(fact_data)
        
    return results
