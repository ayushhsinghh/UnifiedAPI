"""Pure helpers shared by job responses and image workers."""
from datetime import datetime, timezone


def expected_image_keys(visual_suggestions):
    if not isinstance(visual_suggestions, dict):
        return []
    keys = [key for key in ("cover", "overview", "how_it_works", "myth_visual", "truth_visual") if visual_suggestions.get(key)]
    if visual_suggestions.get("history") and "overview" not in keys:
        keys.append("overview")
    return keys


def image_generation_state(document, timeout_seconds, now=None):
    fact = document.get("full_response", {})
    expected = expected_image_keys(fact.get("visual_suggestions", {}))
    images = document.get("images") or fact.get("images") or {}
    statuses = document.get("image_status") or {}
    started = document.get("image_started_at")
    now = now or datetime.now(timezone.utc)
    if started and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    expired = not started or (now - started).total_seconds() >= timeout_seconds
    ready = [key for key in expected if images.get(key)]
    pending = [key for key in expected if key not in ready and statuses.get(key) == "processing" and not expired]
    failed = [key for key in expected if key not in ready and key not in pending]
    status = "not_requested" if not expected else "processing" if pending else "partial" if ready and failed else "failed" if failed else "completed"
    return {"status": status, "expected": expected, "ready": ready, "pending": pending, "failed": failed}
