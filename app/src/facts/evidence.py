"""Normalize source links without claiming that their content was verified."""
from urllib.parse import urlsplit


def safe_source_url(value):
    if not isinstance(value, str):
        return ""
    value = value.strip()
    try:
        parsed = urlsplit(value)
        parsed.port  # Reject malformed ports as well as malformed hosts.
        if (parsed.scheme.lower() in {"https", "http"} and parsed.hostname
                and not parsed.username and not parsed.password
                and "\\" not in value
                and not any(ord(char) < 33 or ord(char) == 127 for char in value)):
            return value
    except ValueError:
        pass
    return ""


def normalize_evidence(fact):
    """Drop malformed sources and dangling IDs; preserve legacy reference strings."""
    sources = []
    ids = set()
    for source in fact.get("sources", []) if isinstance(fact.get("sources"), list) else []:
        if not isinstance(source, dict):
            continue
        source_id = source.get("id")
        title = source.get("title")
        if not isinstance(source_id, str) or not source_id.strip() or source_id in ids:
            continue
        if not isinstance(title, str) or not title.strip():
            continue
        ids.add(source_id)
        sources.append({**source, "url": safe_source_url(source.get("url"))})
    fact["sources"] = sources

    def valid_ids(value):
        return list(dict.fromkeys(item for item in value if isinstance(item, str) and item in ids)) if isinstance(value, list) else []

    citations = []
    for citation in fact.get("claim_citations", []) if isinstance(fact.get("claim_citations"), list) else []:
        if not isinstance(citation, dict) or not isinstance(citation.get("claim"), str):
            continue
        linked = valid_ids(citation.get("source_ids"))
        if linked and citation["claim"].strip():
            citations.append({**citation, "source_ids": linked})
    fact["claim_citations"] = citations
    quote = fact.get("quote")
    if isinstance(quote, dict):
        quote["source_ids"] = valid_ids(quote.get("source_ids"))
    for field in ("debunk_evidence", "common_misconceptions"):
        for item in fact.get(field, []) if isinstance(fact.get(field), list) else []:
            if isinstance(item, dict):
                item["source_ids"] = valid_ids(item.get("source_ids"))
    for field, nested in (("training_guide", "exercises"), ("nutrition_guide", "food_items")):
        guide = fact.get(field)
        if isinstance(guide, dict):
            for item in guide.get(nested, []) if isinstance(guide.get(nested), list) else []:
                if isinstance(item, dict):
                    item["source_ids"] = valid_ids(item.get("source_ids"))
    def normalize_lesson_links(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'source_ids':
                    value[key] = valid_ids(child)
                else:
                    normalize_lesson_links(child)
        elif isinstance(value, list):
            for child in value:
                normalize_lesson_links(child)
    normalize_lesson_links(fact.get('physics_lesson'))
    normalize_lesson_links(fact.get('biology_lesson'))
    normalize_lesson_links(fact.get('psychology_lesson'))
    normalize_lesson_links(fact.get('constitution_lesson'))
    normalize_lesson_links(fact.get('indian_law_lesson'))
    normalize_lesson_links(fact.get('country_profile'))
    normalize_lesson_links(fact.get('india_lesson'))
    return fact
