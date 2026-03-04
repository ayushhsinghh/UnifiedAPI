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


MONGODB_URL = f"mongodb+srv://ayush-admin:{_CREDS}@ayush-api.vq10ryu.mongodb.net/?appName=ayush-api"
DATABASE_NAME = "video_transcriber"
JOBS_COLLECTION = "jobs"
GAME_SESSIONS_COLLECTION = "game_sessions"
GAME_PLAYERS_COLLECTION = "game_players"
USERS_COLLECTION = "users"

# Authentication & Security
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# File storage
UPLOAD_DIR = "/mnt/extra/uploads"
OUTPUT_DIR = "/mnt/extra/outputs"
MODELS_DIR = "/home/ubuntu/models"

# Security
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "change-me-in-production")
MODELS_API_KEY = os.getenv("MODELS_API_KEY", "change-me-in-production")
MAX_UPLOAD_SIZE = 6 * 1024 * 1024 * 1024  # 6 GB

ALLOWED_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
    ".mp3", ".wav", ".aac", ".ogg", ".flac", ".m4a",
})

CORS_METHODS = ["GET", "POST", "DELETE", "OPTIONS", "PUT", "PATCH"]
CORS_HEADERS = [
    "Accept",
    "Accept-Language",
    "Authorization",
    "Content-Type",
    "Origin",
    "X-Requested-With",
    "X-Admin-Key",
    "X-Api-Key",
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

# Telemetry — Oracle APM (OpenTelemetry)
# Set OTEL_APM_ENDPOINT + OTEL_APM_DATA_KEY to enable remote export.
# Leave them empty for console-only (local dev / CI).
#
# OTEL_APM_ENDPOINT  → base data-upload URL from your APM domain details page
#   e.g. https://<ID>.apm-agt.ap-mumbai-1.oci.oraclecloud.com
# OTEL_APM_DATA_KEY  → private data key (required for traces & metrics)
# OTEL_APM_USE_PRIVATE_KEY → "true" (default) sends traces via /private/ path;
#                            "false" uses /public/ path instead
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "video-transcriber")
OTEL_APM_ENDPOINT = os.getenv("OTEL_APM_ENDPOINT", "")           # empty = disabled
OTEL_APM_DATA_KEY = os.getenv("OTEL_APM_DATA_KEY", "")            # private data key
OTEL_APM_USE_PRIVATE_KEY = os.getenv("OTEL_APM_USE_PRIVATE_KEY", "true")  # traces key tier
OTEL_METRIC_EXPORT_INTERVAL_MS = int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL_MS", "60000"))  # 60 s
OTEL_EXCLUDED_URLS = os.getenv("OTEL_EXCLUDED_URLS", "/health,/metrics,/openapi.json")

# ── Generic OTLP Exporter (Grafana Tempo, Jaeger, SigNoz, etc.) ──────────
# Standard OTLP/HTTP — appends /v1/traces and /v1/metrics automatically.
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "")         # e.g. https://otlp-gateway-prod-xxx.grafana.net/otlp
OTLP_AUTH_HEADER = os.getenv("OTLP_AUTH_HEADER", "")    # e.g. "Basic base64encodedcreds" or "Bearer token"

# ── Grafana Loki Logging ──────────────────────────────────────────────────
LOKI_ENDPOINT = os.getenv("LOKI_ENDPOINT", "")
LOKI_USERNAME = os.getenv("LOKI_USERNAME", "")
LOKI_PASSWORD = os.getenv("LOKI_PASSWORD", "")
LOKI_TAGS = {"environment": ENVIRONMENT, "service": "video-transcriber"}


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
