"""
Daily Learning Fact Generator.

Uses Google Gemini with structured JSON output to generate rich,
educational, India-biased facts. Includes retry logic with exponential
backoff and provider fallback. The route handles cached facts from MongoDB.
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
from .schemas import (FACT_RESPONSE_SCHEMA, MYTHBUSTER_RESPONSE_SCHEMA,
                      FITNESS_RESPONSE_SCHEMA, INDIAN_DIET_RESPONSE_SCHEMA, validate_wellness_content)
from .evidence import normalize_evidence
from .prompts import _build_prompt, _build_mythbuster_prompt, _build_wellness_prompt
from .physics import PHYSICS_RESPONSE_SCHEMA, build_physics_prompt, validate_physics_content
from .biology import BIOLOGY_RESPONSE_SCHEMA, build_biology_prompt, validate_biology_content
from .psychology import PSYCHOLOGY_RESPONSE_SCHEMA, build_psychology_prompt, validate_psychology_content
from .learning import LEARNER_INSTRUCTIONS, normalize_learning_level
from .constitution import CONSTITUTION_RESPONSE_SCHEMA, build_constitution_prompt, validate_constitution_content
from .constitution_sources import enrich_constitution_text
from .indian_laws import INDIAN_LAWS_RESPONSE_SCHEMA, build_indian_laws_prompt, validate_indian_laws_content
from .india import INDIA_RESPONSE_SCHEMA, INDIA_IMAGE_INSTRUCTIONS, build_india_prompt, validate_india_content, prepare_india_media
from .image_policy import IMAGE_INSTRUCTIONS, IMAGE_KEYS, validate_image_plan
from .country import COUNTRY_RESPONSE_SCHEMA, COUNTRY_IMAGE_INSTRUCTIONS, build_country_prompt, validate_country_content, enrich_country_identity

# ── Retry constants ──────────────────────────────────────────────────────

_MAX_RETRIES = 3
_BACKOFF_SECONDS = [1, 2, 4]
_REQUEST_TIMEOUT_SECONDS = cfg.FACT_REQUEST_TIMEOUT_SECONDS


# ── Main generation function ────────────────────────────────────────────


async def generate_daily_fact(
    category: str,
    blocklist: Optional[List[str]] = None,
    generation_metadata: Optional[dict] = None,
) -> dict:
    """
    Generate a rich, structured educational fact using Google Gemini.

    Args:
        category: The fact category (must be from SUPPORTED_CATEGORIES
                  or a custom sanitized category).
        blocklist: List of short topic keys to avoid (dedup).
        generation_metadata: Optional output dictionary for actual provider and model.

    Returns:
        A dict matching the FACT_RESPONSE_SCHEMA structure.

    Raises:
        Provider failures are retried; returns None when all attempts fail.
    """
    if blocklist is None:
        blocklist = []

    if category == 'india':
        prompt = build_india_prompt(blocklist)
        response_schema = INDIA_RESPONSE_SCHEMA
    elif category == 'country':
        prompt = build_country_prompt(blocklist)
        response_schema = COUNTRY_RESPONSE_SCHEMA
    elif category == 'indian_laws':
        prompt = build_indian_laws_prompt(blocklist)
        response_schema = INDIAN_LAWS_RESPONSE_SCHEMA
    elif category == 'indian_constitution':
        prompt = build_constitution_prompt(blocklist)
        response_schema = CONSTITUTION_RESPONSE_SCHEMA
    elif category == 'psychology':
        prompt = build_psychology_prompt(blocklist)
        response_schema = PSYCHOLOGY_RESPONSE_SCHEMA
    elif category == 'biology':
        prompt = build_biology_prompt(blocklist)
        response_schema = BIOLOGY_RESPONSE_SCHEMA
    elif category == 'physics':
        prompt = build_physics_prompt(blocklist)
        response_schema = PHYSICS_RESPONSE_SCHEMA
    elif category in {"fitness", "home_workouts", "indian_diet", "nutrition_myths"}:
        prompt = _build_wellness_prompt(category, blocklist)
        response_schema = (MYTHBUSTER_RESPONSE_SCHEMA if category == "nutrition_myths"
                           else INDIAN_DIET_RESPONSE_SCHEMA if category == "indian_diet"
                           else FITNESS_RESPONSE_SCHEMA)
    elif category in {"mythbusters", "digital_myths", "money_myths", "environment_myths", "science_myths"}:
        prompt = _build_mythbuster_prompt(blocklist, category)
        response_schema = MYTHBUSTER_RESPONSE_SCHEMA
    else:
        prompt = _build_prompt(category, blocklist)
        response_schema = FACT_RESPONSE_SCHEMA

    # Every provider and fallback receives the same non-expert audience contract.
    audience = LEARNER_INSTRUCTIONS if category != 'country' else LEARNER_INSTRUCTIONS.replace('Teach ONE interesting fact or useful new idea', 'Teach ONE country through connected useful ideas').replace('Aim for a focused 3-6 minute read, not an encyclopedia chapter or exam syllabus.', 'A country portrait can span an accessible 8-15 minute read.').replace('Before returning, check that a newcomer can explain the central fact in one sentence.', 'Before returning, check that a newcomer can describe the country in a few sentences.')
    if category == 'india':
        audience = audience.replace('Aim for a focused 3-6 minute read, not an encyclopedia chapter or exam syllabus.', 'Explore one focused India topic in an accessible 7-10 minute read.')
    prompt += '\n\n' + audience + '\n\n' + (INDIA_IMAGE_INSTRUCTIONS if category == 'india' else COUNTRY_IMAGE_INSTRUCTIONS if category == 'country' else IMAGE_INSTRUCTIONS)
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

                response = await asyncio.wait_for(client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={
                        "temperature": 0.9,
                        "top_p": 0.95,
                        "top_k": 40,
                        "response_mime_type": "application/json",
                        "response_schema": response_schema,
                    },
                ), timeout=_REQUEST_TIMEOUT_SECONDS)
                fact = response.parsed
            else:
                openai_client = openai.AsyncOpenAI(api_key=cfg.OPENAI_API_KEY)
                logger.debug(
                    "OpenAI fallback generation attempt %d using model '%s' for category '%s'",
                    attempt + 1, model_name, category,
                )
                
                openai_prompt = prompt + "\n\nRETURN YOUR RESPONSE AS A VALID JSON OBJECT MATCHING THIS SCHEMA EXACTLY:\n" + json.dumps(response_schema)
                
                response = await asyncio.wait_for(openai_client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": openai_prompt}],
                    response_format={"type": "json_object"},
                ), timeout=_REQUEST_TIMEOUT_SECONDS)
                fact_str = response.choices[0].message.content
                fact = json.loads(fact_str) if fact_str else None

            if (isinstance(fact, dict) and fact.get("headline_fact") and normalize_learning_level(fact)
                    and validate_image_plan(fact, myth=category in {'mythbusters', 'digital_myths', 'money_myths', 'environment_myths', 'science_myths', 'nutrition_myths'}) and validate_wellness_content(fact, category)
                    and (category != 'physics' or validate_physics_content(fact))
                    and (category != 'biology' or validate_biology_content(fact))
                    and (category != 'psychology' or validate_psychology_content(fact))
                    and (category != 'indian_constitution' or validate_constitution_content(fact))
                    and (category != 'indian_laws' or validate_indian_laws_content(fact))
                    and (category != 'country' or validate_country_content(fact))
                    and (category != 'india' or validate_india_content(fact))):
                normalize_evidence(fact)
                fact["category"] = category
                if category == 'india':
                    prepare_india_media(fact)
                if category == 'country':
                    enrich_country_identity(fact)
                if category == 'indian_laws':
                    # Never trust model-generated verification or retrieval metadata.
                    fact['indian_laws_validation'] = {'structure_checked': True,
                        'source_verification': 'not_performed', 'legal_currency_check': 'not_performed',
                        'retrieved_sources': [], 'checked_at': None}
                    fact['visual_suggestions'] = {key: value for key, value in fact['visual_suggestions'].items()
                                                  if key in IMAGE_KEYS and value.strip()}
                if category == 'physics':
                    fact['physics_validation'] = {
                        'arithmetic_checked': bool(fact['physics_lesson']['worked_example']['calculations']),
                        'source_verification': 'not_performed',
                        'scientific_review': 'not_performed',
                    }
                    # Preserve the complete validated image plan, including optional explanatory slots.
                    fact['visual_suggestions'] = {key: value for key, value in fact['visual_suggestions'].items()
                                                  if key in IMAGE_KEYS and value.strip()}
                if category == 'biology':
                    fact['biology_validation'] = {'structure_checked': True, 'source_verification': 'not_performed', 'scientific_review': 'not_performed'}
                    fact['visual_suggestions'] = {key: value for key, value in fact['visual_suggestions'].items()
                                                  if key in IMAGE_KEYS and value.strip()}
                if category == 'psychology':
                    fact['psychology_validation'] = {'structure_checked': True, 'source_verification': 'not_performed', 'scientific_review': 'not_performed'}
                    fact['visual_suggestions'] = {key: value for key, value in fact['visual_suggestions'].items()
                                                  if key in IMAGE_KEYS and value.strip()}
                if category == 'indian_constitution':
                    await enrich_constitution_text(fact)
                    fact['visual_suggestions'] = {key: value for key, value in fact['visual_suggestions'].items()
                                                  if key in IMAGE_KEYS and value.strip()}
                if generation_metadata is not None:
                    generation_metadata.update(provider="gemini" if model_name.startswith("gemini") else "openai", model=model_name)
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

    # The route selects a cached fact after all providers fail.
    logger.warning(
        "All %d generation attempts failed for category '%s'. Last error: %s",
        _MAX_RETRIES + 1, category, last_error,
    )
    return None
