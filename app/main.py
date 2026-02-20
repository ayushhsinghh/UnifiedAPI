"""
Video Transcriber & Imposter Game — Application Factory.

This is the single entry point. It wires up:
  - Logging
  - Middleware stack (Request-ID → Security headers → Trusted hosts → CORS)
  - Database connection
  - APIRouter modules (transcription, game, admin)
  - Static file mounts & homepage
  - CLI (argparse for host/port/SSL)
"""

import argparse
import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from commons import limiter
from configs.config import get_config
from logging_config import setup_logging
from security import RequestIdMiddleware, SecurityHeadersMiddleware

# ── Logging ──────────────────────────────────────────────────────────────
setup_logging()
logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────
cfg = get_config()

# ── FastAPI App ──────────────────────────────────────────────────────────
app = FastAPI(
    title="Video Transcriber & Imposter Game API",
    docs_url="/docs" if cfg.DOCS_ENABLED else None,
    redoc_url="/redoc" if cfg.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if cfg.DOCS_ENABLED else None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── Middleware Stack (outermost first) ───────────────────────────────────
app.add_middleware(RequestIdMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=cfg.ALLOWED_HOSTS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=cfg.CORS_METHODS,
    allow_headers=cfg.CORS_HEADERS,
)

# ── Directories ──────────────────────────────────────────────────────────
os.makedirs(cfg.UPLOAD_DIR, exist_ok=True)
os.makedirs(cfg.OUTPUT_DIR, exist_ok=True)

# ── Database ─────────────────────────────────────────────────────────────
try:
    from src.database.connection import DatabaseManager
    db_manager = DatabaseManager()
    logger.info("Database manager initialized successfully")
except Exception as exc:
    logger.warning(
        "Failed to initialize database: %s. "
        "The application will continue with limited functionality.",
        exc,
    )

# ── Routers ──────────────────────────────────────────────────────────────
from src.routes.transcription_routes import router as transcription_router  # noqa: E402
from src.routes.game_routes import router as game_router  # noqa: E402
from src.routes.admin_routes import router as admin_router  # noqa: E402

app.include_router(transcription_router)
app.include_router(game_router)
app.include_router(admin_router)

# ── Static Files ─────────────────────────────────────────────────────────
_base_dir = os.path.dirname(__file__)

# app.mount(
#     "/frontend",
#     StaticFiles(directory=os.path.join(_base_dir, "frontend")),
#     name="frontend",
# )
# app.mount(
#     "/guessGame",
#     StaticFiles(directory=os.path.join(_base_dir, "guessGame")),
#     name="guessGame",
# )

# ── Homepage ─────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
@limiter.limit("30/minute")
def home(request: Request) -> str:
    """Serve the homepage from the templates directory."""
    template_path = os.path.join(_base_dir, "templates", "home.html")
    try:
        with open(template_path, "r", encoding="utf-8") as template_file:
            return template_file.read()
    except FileNotFoundError:
        logger.error("Template not found at %s", template_path)
        return (
            "<html><body>"
            "<h1>Video Transcriber API</h1>"
            "<p>Homepage template not found.</p>"
            "</body></html>"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Run Video Transcriber")
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--reload", action="store_true",
        help="Enable auto-reload on code changes",
    )
    parser.add_argument(
        "--cert-file", default=None,
        help="Path to SSL certificate file (enables HTTPS)",
    )
    parser.add_argument(
        "--key-file", default=None,
        help="Path to SSL private key file (required with --cert-file)",
    )
    parser.add_argument(
        "--env", default=None,
        choices=["development", "production"],
        help="Override the ENVIRONMENT env variable",
    )

    args = parser.parse_args()

    if args.env:
        os.environ["ENVIRONMENT"] = args.env
        logger.info("Environment overridden to '%s' via --env flag", args.env)

    if bool(args.cert_file) != bool(args.key_file):
        logger.error(
            "Both --cert-file and --key-file must be provided together"
        )
        sys.exit(1)

    protocol = "HTTPS" if args.cert_file else "HTTP"
    logger.info("Starting %s server on %s:%d", protocol, args.host, args.port)
    if args.cert_file:
        logger.info("  Local: https://localhost:%d", args.port)
        logger.info(
            "  SSL/TLS enabled with certificate from: %s", args.cert_file
        )
    else:
        logger.info("  Local: http://localhost:%d", args.port)

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
        ssl_certfile=args.cert_file,
        ssl_keyfile=args.key_file,
        limit_concurrency=1000,
        limit_max_requests=10000,
    )