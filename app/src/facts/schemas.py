# Additive evidence fields keep existing sources_or_references strings compatible.
_SOURCE_IDS_SCHEMA = {"type": "ARRAY", "items": {"type": "STRING"}}
_SOURCES_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "title": {"type": "STRING"},
            "url": {"type": "STRING"},
            "author": {"type": "STRING"},
            "published_date": {"type": "STRING"},
        },
        "required": ["id", "title", "url"],
    },
}
_CLAIM_CITATIONS_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "claim": {"type": "STRING"},
            "section": {"type": "STRING"},
            "source_ids": _SOURCE_IDS_SCHEMA,
        },
        "required": ["claim", "section", "source_ids"],
    },
}

_TIMELINE_ITEM_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "year": {"type": "STRING"},
        "event": {"type": "STRING"},
    },
    "required": ["year", "event"],
}

_BREAKDOWN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "detailed_processes": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "steps": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"}
                    }
                },
                "required": ["title", "description", "steps"]
            }
        },
        "real_world_application": {"type": "STRING"},
        "fascinating_trivia": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
    "required": [
        "detailed_processes",
        "real_world_application",
        "fascinating_trivia",
    ],
}

FACT_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        # Core Fact
        "category": {"type": "STRING"},
        "topic": {"type": "STRING"},
        "headline_fact": {"type": "STRING"},
        "summary": {"type": "STRING"},
        "did_you_know": {"type": "STRING"},

        # Deep Dive — the main educational content
        "history": {"type": "STRING"},
        "core_mechanics": {"type": "STRING"},
        "why_it_matters": {"type": "STRING"},
        "in_depth_breakdown": _BREAKDOWN_SCHEMA,

        # India-specific deep context
        "impact_on_india": {"type": "STRING"},
        "cultural_significance": {"type": "STRING"},
        "common_misconceptions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "myth": {"type": "STRING"},
                    "reality": {"type": "STRING"},
                    "source_ids": _SOURCE_IDS_SCHEMA,
                    "evidence": {"type": "STRING"}
                },
                "required": ["myth", "reality", "evidence"]
            }
        },

        # Key Highlights
        "key_year": {"type": "STRING"},
        "key_figure": {"type": "STRING"},
        "key_stat": {"type": "STRING"},
        "quote": {
            "type": "OBJECT",
            "properties": {
                "text": {"type": "STRING"},
                "source_ids": _SOURCE_IDS_SCHEMA,
                "confidence": {"type": "STRING", "enum": ["verified", "unverified"]}
            },
            "required": ["text", "confidence"]
        },
        "global_comparison": {
            "type": "OBJECT",
            "properties": {
                "summary": {"type": "STRING"},
                "comparisons": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "country": {"type": "STRING"},
                            "comparison_point": {"type": "STRING"}
                        },
                        "required": ["country", "comparison_point"]
                    }
                }
            },
            "required": ["summary", "comparisons"]
        },

        # Timeline
        "timeline": {
            "type": "ARRAY",
            "items": _TIMELINE_ITEM_SCHEMA,
        },

        # Learning
        "learning_takeaways": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },

        # Metadata & UI Helpers
        "content_freshness": {
            "type": "STRING",
            "enum": ["evergreen", "time-sensitive"]
        },
        "emoji_icon": {"type": "STRING"},
        "difficulty_level": {"type": "STRING"},
        "region": {"type": "STRING"},
        "fun_rating": {"type": "NUMBER"},
        "read_time_seconds": {"type": "NUMBER"},
        "tags": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "related_categories": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "visual_suggestions": {
            "type": "OBJECT",
            "properties": {
                "cover": {"type": "STRING"},
                "overview": {"type": "STRING"},
                "how_it_works": {"type": "STRING"},
            },
            "required": ["cover", "overview", "how_it_works"]
        },
        "share_text": {"type": "STRING"},

        # Sources
        "sources": _SOURCES_SCHEMA,
        "claim_citations": _CLAIM_CITATIONS_SCHEMA,
        "sources_or_references": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
    "required": [
        "category", "topic", "headline_fact", "summary", "did_you_know",
        "history", "core_mechanics", "why_it_matters",
        "in_depth_breakdown",
        "impact_on_india", "cultural_significance", "common_misconceptions",
        "key_year", "key_figure", "key_stat", "quote", "global_comparison",
        "timeline",
        "learning_takeaways",
        "emoji_icon", "difficulty_level", "region", "fun_rating",
        "read_time_seconds", "tags", "related_categories",
        "visual_suggestions", "share_text", "content_freshness",
        "sources_or_references", "sources", "claim_citations",
    ],
}

_EVIDENCE_ITEM_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "study": {"type": "STRING"},
        "year": {"type": "STRING"},
        "finding": {"type": "STRING"},
        "source": {"type": "STRING"},
        "source_ids": _SOURCE_IDS_SCHEMA,
    },
    "required": ["study", "year", "finding", "source"],
}

MYTHBUSTER_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        # Core identification
        "category": {"type": "STRING"},
        "topic": {"type": "STRING"},
        "headline_fact": {"type": "STRING"},
        "summary": {"type": "STRING"},
        "did_you_know": {"type": "STRING"},

        # Myth-specific fields
        "myth_statement": {"type": "STRING"},
        "verdict": {
            "type": "STRING",
            "enum": ["BUSTED", "PARTIALLY_TRUE", "PLAUSIBLE", "TRUE"],
        },
        "verdict_confidence": {
            "type": "STRING",
            "enum": ["strong", "moderate", "emerging"],
        },
        "myth_origin": {"type": "STRING"},
        "spread_psychology": {"type": "STRING"},
        "grain_of_truth": {"type": "STRING"},
        "the_reality": {"type": "STRING"},
        "counter_arguments": {"type": "STRING"},
        "how_to_explain": {"type": "STRING"},
        "myth_sub_category": {
            "type": "STRING",
            "enum": [
                "health", "science", "history", "nutrition",
                "psychology", "society", "technology", "nature",
            ],
        },
        "prevalence": {"type": "STRING"},

        # Structured evidence
        "debunk_evidence": {
            "type": "ARRAY",
            "items": _EVIDENCE_ITEM_SCHEMA,
        },

        # Misconceptions (can still have related myths)
        "common_misconceptions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "myth": {"type": "STRING"},
                    "reality": {"type": "STRING"},
                    "source_ids": _SOURCE_IDS_SCHEMA,
                    "evidence": {"type": "STRING"},
                },
                "required": ["myth", "reality", "evidence"],
            },
        },

        # Timeline (myth evolution)
        "timeline": {
            "type": "ARRAY",
            "items": _TIMELINE_ITEM_SCHEMA,
        },

        # Learning
        "learning_takeaways": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },

        # Key highlights
        "key_figure": {"type": "STRING"},
        "key_stat": {"type": "STRING"},
        "quote": {
            "type": "OBJECT",
            "properties": {
                "text": {"type": "STRING"},
                "source_ids": _SOURCE_IDS_SCHEMA,
                "confidence": {
                    "type": "STRING",
                    "enum": ["verified", "unverified"],
                },
            },
            "required": ["text", "confidence"],
        },

        # Metadata & UI helpers
        "content_freshness": {
            "type": "STRING",
            "enum": ["evergreen", "time-sensitive"],
        },
        "emoji_icon": {"type": "STRING"},
        "difficulty_level": {"type": "STRING"},
        "region": {"type": "STRING"},
        "fun_rating": {"type": "NUMBER"},
        "read_time_seconds": {"type": "NUMBER"},
        "tags": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "related_categories": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "visual_suggestions": {
            "type": "OBJECT",
            "properties": {
                "cover": {"type": "STRING"},
                "myth_visual": {"type": "STRING"},
                "truth_visual": {"type": "STRING"},
            },
            "required": ["cover", "myth_visual", "truth_visual"],
        },
        "share_text": {"type": "STRING"},

        # Sources
        "sources": _SOURCES_SCHEMA,
        "claim_citations": _CLAIM_CITATIONS_SCHEMA,
        "sources_or_references": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
    "required": [
        "category", "topic", "headline_fact", "summary", "did_you_know",
        "myth_statement", "verdict", "verdict_confidence",
        "myth_origin", "spread_psychology", "grain_of_truth",
        "the_reality", "counter_arguments", "how_to_explain",
        "myth_sub_category", "prevalence", "debunk_evidence",
        "common_misconceptions", "timeline", "learning_takeaways",
        "key_figure", "key_stat", "quote",
        "emoji_icon", "difficulty_level", "region", "fun_rating",
        "read_time_seconds", "tags", "related_categories",
        "visual_suggestions", "share_text", "content_freshness",
        "sources_or_references", "sources", "claim_citations",
    ],
}


# Category-specific contracts keep general facts compatible with older clients.
def _object(properties, required=None):
    return {"type": "OBJECT", "properties": properties,
            "required": list(properties) if required is None else required}


def _strings():
    return {"type": "ARRAY", "items": {"type": "STRING"}}


def _items(item):
    return {"type": "ARRAY", "items": item}


_TEXT = {"type": "STRING"}
_NUMBER = {"type": "NUMBER", "nullable": True, "minimum": 0}
_EXERCISE_SCHEMA = _object({
    "name": _TEXT, "search_query": _TEXT, "sets": _TEXT, "reps": _TEXT,
    "rest_seconds": _NUMBER, "steps": _strings(), "easier_option": _TEXT,
    "progression": _TEXT, "source_ids": _strings(),
})
_TRAINING_GUIDE_SCHEMA = _object({
    "goal": _TEXT, "level": _TEXT, "duration_minutes": _NUMBER,
    "equipment": _strings(), "frequency": _TEXT, "warm_up": _strings(),
    "exercises": _items(_EXERCISE_SCHEMA), "cool_down": _strings(),
    "recovery": _TEXT, "safety_notes": _strings(),
})
_NUTRITION_GUIDE_SCHEMA = _object({
    "goal": _TEXT,
    "food_items": _items(_object({
        "name": _TEXT, "portion": _TEXT, "preparation": _TEXT,
        "energy_kcal": _NUMBER, "protein_g": _NUMBER, "carbs_g": _NUMBER,
        "fat_g": _NUMBER, "fiber_g": _NUMBER, "key_micronutrients": _strings(),
        "source_ids": _strings(),
    })),
    "meal_plan": _items(_object({
        "meal": _TEXT, "foods": _strings(), "portion": _TEXT, "why": _TEXT,
    })),
    "swaps": _items(_object({"instead_of": _TEXT, "try_this": _TEXT, "reason": _TEXT})),
    "practical_tips": _strings(), "limitations": _strings(),
})


def _wellness_schema(field, schema):
    from copy import deepcopy
    base = deepcopy(FACT_RESPONSE_SCHEMA)
    # A practical guide takes priority over mandatory historical filler.
    for key in ("history", "impact_on_india", "cultural_significance", "key_year",
                "key_figure", "key_stat", "quote", "global_comparison", "timeline"):
        base["properties"].pop(key, None)
        base["required"].remove(key)
    base["properties"][field] = schema
    base["required"].append(field)
    return base


FITNESS_RESPONSE_SCHEMA = _wellness_schema("training_guide", _TRAINING_GUIDE_SCHEMA)
INDIAN_DIET_RESPONSE_SCHEMA = _wellness_schema("nutrition_guide", _NUTRITION_GUIDE_SCHEMA)


def validate_wellness_content(fact, category):
    """Validate practical fields for JSON-only fallback providers, too."""
    import math

    def validate(value, schema):
        if value is None and schema.get("nullable"):
            return True
        kind = schema["type"]
        if kind == "OBJECT":
            return (isinstance(value, dict)
                    and all(key in value for key in schema.get("required", []))
                    and all(validate(value[key], child) for key, child in schema["properties"].items() if key in value))
        if kind == "ARRAY":
            return isinstance(value, list) and all(validate(item, schema["items"]) for item in value)
        if kind == "NUMBER":
            return (type(value) in (int, float) and math.isfinite(value)
                    and value >= schema.get("minimum", float("-inf")))
        if kind == "STRING":
            return isinstance(value, str) and ("enum" not in schema or value in schema["enum"])
        return True

    if category in {"fitness", "home_workouts"}:
        return validate(fact.get("training_guide"), _TRAINING_GUIDE_SCHEMA)
    if category == "indian_diet":
        return validate(fact.get("nutrition_guide"), _NUTRITION_GUIDE_SCHEMA)
    if category == "nutrition_myths":
        return all(validate(fact.get(key), MYTHBUSTER_RESPONSE_SCHEMA["properties"][key])
                   for key in ("myth_statement", "verdict", "verdict_confidence", "the_reality", "how_to_explain", "debunk_evidence"))
    return True
