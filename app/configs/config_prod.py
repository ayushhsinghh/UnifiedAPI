"""
Production environment configuration.

These are the baseline defaults. Local overrides live in config_local.py.
"""

# FastAPI docs are disabled in production
DOCS_ENABLED = False

CORS_ORIGINS = [
    "https://game.ayush.ltd",
    "https://subs.ayush.ltd",
    "https://ayush.ltd",
]

ALLOWED_HOSTS = [
    "game.ayush.ltd",
    "api.ayush.ltd",
    "subs.ayush.ltd",
    "ayush.ltd",
    "localhost",
    "127.0.0.1",
]
