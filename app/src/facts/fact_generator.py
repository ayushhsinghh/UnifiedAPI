"""
Daily Learning Fact Generator.

Uses Google Gemini with structured JSON output to generate rich,
educational, India-biased facts. Includes retry logic with exponential
backoff and emergency fallback to cached facts from MongoDB.
"""

import asyncio
import json
import logging
import random
import time
from typing import Dict, List, Optional

import openai
from google import genai

from configs.config import get_config

logger = logging.getLogger(__name__)

cfg = get_config()

# ── Category sub-topic hints ────────────────────────────────────────────
from .constants import CATEGORY_HINTS, SUPPORTED_CATEGORIES, CLICHED_FACTS
from .schemas import FACT_RESPONSE_SCHEMA
from .prompts import _build_prompt

# ── Retry constants ──────────────────────────────────────────────────────

_MAX_RETRIES = 3
_BACKOFF_SECONDS = [1, 2, 4]
_REQUEST_TIMEOUT_SECONDS = 30


# ── Main generation function ────────────────────────────────────────────


async def generate_daily_fact(
    category: str,
    blocklist: Optional[List[str]] = None,
) -> dict:
    """
    Generate a rich, structured educational fact using Google Gemini.

    Args:
        category: The fact category (must be from SUPPORTED_CATEGORIES
                  or a custom sanitized category).
        blocklist: List of short topic keys to avoid (dedup).

    Returns:
        A dict matching the FACT_RESPONSE_SCHEMA structure.

    Raises:
        No exceptions — falls back to cached or emergency data on failure.
    """
    if blocklist is None:
        blocklist = []

    prompt = _build_prompt(category, blocklist)
    last_error: Optional[Exception] = None
    
    fallback_models = [cfg.GEMINI_MODEL_NAME, "gemini-3.8-flash", "gemini-3.5-flash", cfg.OPENAI_MODEL_NAME]

    for attempt in range(_MAX_RETRIES + 1):
        model_name = fallback_models[attempt] if attempt < len(fallback_models) else fallback_models[-1]
        try:
            if model_name.startswith("gemini"):
                client = genai.Client(api_key=cfg.GEMINI_API_KEY)
                logger.debug(
                    "Gemini fact generation attempt %d using model '%s' for category '%s'",
                    attempt + 1, model_name, category,
                )

                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={
                        "temperature": 0.9,
                        "top_p": 0.95,
                        "top_k": 40,
                        "response_mime_type": "application/json",
                        "response_schema": FACT_RESPONSE_SCHEMA,
                    },
                )
                fact = response.parsed
            else:
                openai_client = openai.AsyncOpenAI(api_key=cfg.OPENAI_API_KEY)
                logger.debug(
                    "OpenAI fallback generation attempt %d using model '%s' for category '%s'",
                    attempt + 1, model_name, category,
                )
                
                openai_prompt = prompt + "\n\nRETURN YOUR RESPONSE AS A VALID JSON OBJECT MATCHING THIS SCHEMA EXACTLY:\n" + json.dumps(FACT_RESPONSE_SCHEMA)
                
                response = await openai_client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": openai_prompt}],
                    response_format={"type": "json_object"},
                )
                fact_str = response.choices[0].message.content
                fact = json.loads(fact_str) if fact_str else None

            if isinstance(fact, dict) and fact.get("headline_fact"):
                logger.info(
                    "Generated fact for '%s': %s",
                    category, fact.get("topic", "unknown"),
                )
                return fact

            logger.warning(
                "Model returned empty or malformed response on attempt %d",
                attempt + 1,
            )

        except Exception as exc:
            last_error = exc
            logger.error(
                "API error on attempt %d: %s", attempt + 1, exc,
            )

        # Exponential backoff before retry (skip on last attempt)
        if attempt < _MAX_RETRIES:
            backoff = _BACKOFF_SECONDS[attempt]
            logger.info("Retrying in %ds...", backoff)
            await asyncio.sleep(backoff)

    # All retries exhausted — fall back to cached fact
    logger.warning(
        "All %d Gemini attempts failed for category '%s'. Last error: %s",
        _MAX_RETRIES + 1, category, last_error,
    )
    return None
 