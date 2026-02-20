"""
Development / local environment configuration overrides.

Only values that DIFFER from production need to be declared here.
The base config.py merges these on top of the production defaults.
"""

# FastAPI docs are enabled in development
DOCS_ENABLED = True

# Relaxed CORS for local development
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "https://game.ayush.ltd",
    "https://subs.ayush.ltd",
    "https://ayush.ltd",
]

# Trusted hosts include localhost
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "game.ayush.ltd",
    "api.ayush.ltd",
    "subs.ayush.ltd",
    "ayush.ltd",
]
