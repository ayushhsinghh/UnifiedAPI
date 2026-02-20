"""
Centralized configuration loader.

Reads the ENVIRONMENT env-var and merges the correct environment module
(config_prod or config_local) into a single settings namespace.

Usage:
    from configs.config import get_config
    cfg = get_config()
    print(cfg.MONGODB_URL)
"""

import os
import importlib
import logging
from types import SimpleNamespace

logger = logging.getLogger(__name__)

# ── Environment detection ────────────────────────────────────────────────
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

# ── Shared constants (environment-independent) ───────────────────────────

_CREDS = os.getenv("CREDS", "")

# Database
MONGODB_URL = f"mongodb://admin:{_CREDS}@127.0.0.1:27017/video_transcriber?authSource=admin"
DATABASE_NAME = "video_transcriber"
JOBS_COLLECTION = "jobs"
GAME_SESSIONS_COLLECTION = "game_sessions"
GAME_PLAYERS_COLLECTION = "game_players"

# File storage
UPLOAD_DIR = "/mnt/extra/uploads"
OUTPUT_DIR = "/mnt/extra/outputs"

# Security
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "change-me-in-production")
MAX_UPLOAD_SIZE = 5 * 1024 * 1024 * 1024  # 5 GB

ALLOWED_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
    ".mp3", ".wav", ".aac", ".ogg", ".flac", ".m4a",
})

CORS_METHODS = ["GET", "POST", "DELETE", "OPTIONS"]
CORS_HEADERS = [
    "Accept",
    "Accept-Language",
    "Authorization",
    "Content-Type",
    "Origin",
    "X-Requested-With",
    "X-Admin-Key",
    "X-Request-ID",
]

# Gemini / topic generation
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL_NAME = "gemini-3-flash-preview"

# Logging
LOG_FILE_APP = "app.log"
LOG_FILE_ERRORS = "errors.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 5

# Game timing defaults
GAME_DISCUSSION_TIME_SECONDS = 180
GAME_VOTING_TIME_SECONDS = 60
HEARTBEAT_TIMEOUT_SECONDS = 45
SESSION_TTL_SECONDS = 21600       # 6 hours
PLAYER_TTL_SECONDS = 3600         # 1 hour
OLD_GAME_THRESHOLD_MINUTES = 30
AVAILABLE_GAME_WINDOW_MINUTES = 10

# Whisper defaults
WHISPER_DEFAULT_MODEL = "medium"
WHISPER_ALLOWED_MODELS = frozenset({"tiny", "base", "small", "medium", "large-v3"})


# ── Config loader ────────────────────────────────────────────────────────

_config_cache = None


def get_config() -> SimpleNamespace:
    """
    Return a merged configuration namespace.

    Environment-specific values from config_local or config_prod
    override the shared defaults defined above.
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    # Start with all module-level constants
    base = {
        key: value
        for key, value in globals().items()
        if key.isupper() and not key.startswith("_")
    }

    # Overlay environment-specific settings
    env_module_name = (
        "configs.config_local" if ENVIRONMENT == "development"
        else "configs.config_prod"
    )
    try:
        env_module = importlib.import_module(env_module_name)
        for key in dir(env_module):
            if key.isupper():
                base[key] = getattr(env_module, key)
        logger.info("Loaded configuration from %s", env_module_name)
    except ImportError:
        logger.warning(
            "Environment config '%s' not found; using shared defaults.",
            env_module_name,
        )

    _config_cache = SimpleNamespace(**base)
    return _config_cache
