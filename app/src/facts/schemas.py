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
        "sources_or_references",
    ],
}

