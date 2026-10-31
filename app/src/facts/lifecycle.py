"""Pure helpers shared by job responses and image workers."""
from datetime import datetime, timezone


def expected_image_keys(visual_suggestions):
    if not isinstance(visual_suggestions, dict):
        return []
    keys = [key for key in ("cover", "overview", "how_it_works", "explanation_2", "explanation_3", "explanation_4", "explanation_5", "explanation_6", "myth_visual", "truth_visual") if visual_suggestions.get(key)]
    if visual_suggestions.get("history") and "overview" not in keys:
        keys.append("overview")
    return keys


def fact_image_keys(fact):
    keys=expected_image_keys(fact.get('visual_suggestions',{}))
    if fact.get('article_type')=='food_lesson':
        from src.facts.food import food_photo_entries
        return [key for key in ('cover','overview') if fact.get('visual_suggestions',{}).get(key)]+[p['key'] for p in food_photo_entries(fact)]+[f'food_scene_{n}' for n in range(6)]
    if fact.get('article_type')=='india_lesson':
        from src.facts.india import india_photo_entries, india_carousel_keys
        return [key for key in ('cover','overview') if fact.get('visual_suggestions',{}).get(key)] + [p['key'] for p in india_photo_entries(fact)] + india_carousel_keys(fact)
    if fact.get('article_type')=='country_profile' and fact.get('country_media',{}).get('photo_layout') in ('contextual_v1','contextual_v2'):
        from src.facts.country_photos import country_scene_plan
        if fact.get('country_media',{}).get('photo_ranking_version')==1:
            keys=[key for key in keys if key not in ('explanation_3','explanation_4','explanation_5','explanation_6')]
            keys.extend(f'country_ranked_{n}' for n in range(18))
        else:keys=list(dict.fromkeys(keys+list(country_scene_plan(fact.get('country_profile',{}),extended=fact['country_media']['photo_layout']=='contextual_v2'))))
        from src.facts.country_media_plan import country_photo_entries
        keys.extend(item['key'] for item in country_photo_entries(fact.get('country_profile',{}),extended=fact['country_media']['photo_layout']=='contextual_v2'))
    return keys


def image_generation_state(document, timeout_seconds, now=None):
    fact = document.get("full_response", {})
    expected = fact_image_keys(fact)
    images = document.get("images") or fact.get("images") or {}
    statuses = document.get("image_status") or {}
    expected=[key for key in expected if statuses.get(key)!='not_requested']
    if fact.get('article_type')=='food_lesson' or any(fact.get(key,{}).get('photo_ranking_version')==1 for key in ('india_media','country_media')):
        timeout_seconds=max(timeout_seconds,720)
    started = document.get("image_started_at")
    now = now or datetime.now(timezone.utc)
    if started and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    expired = not started or (now - started).total_seconds() >= timeout_seconds
    ready = [key for key in expected if images.get(key)]
    pending = [key for key in expected if key not in ready and statuses.get(key) == "processing" and not expired]
    failed = [key for key in expected if key not in ready and key not in pending]
    status = "not_requested" if not expected else "processing" if pending else "partial" if ready and failed else "failed" if failed else "completed"
    return {"status": status, "expected": expected, "ready": ready, "pending": pending, "failed": failed,"timeout_seconds":timeout_seconds}
