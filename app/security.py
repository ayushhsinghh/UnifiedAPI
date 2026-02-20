"""
Security utilities for the FastAPI application.
Provides middlewares, validators, and helpers for hardening the server.
"""

import os
import re
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi import HTTPException

from configs.config import get_config

logger = logging.getLogger(__name__)

cfg = get_config()

# --------------- Input Validation Patterns ---------------

JOB_ID_PATTERN = re.compile(r"^job_[a-z0-9]{4}$")
SESSION_ID_PATTERN = re.compile(r"^[A-Z0-9]{5}$")
PLAYER_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9 _\-]{1,30}$")
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


# --------------- Middlewares ---------------


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject standard security headers on every response."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique X-Request-ID to every request / response."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# --------------- Validators ---------------


def validate_job_id(job_id: str) -> str:
    """Validate and return a safe job_id, or raise 400."""
    if not JOB_ID_PATTERN.match(job_id):
        logger.warning("Rejected invalid job_id: %r", job_id)
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    return job_id


def validate_session_id(session_id: str) -> str:
    """Validate and return a safe session_id, or raise 400."""
    if not SESSION_ID_PATTERN.match(session_id):
        logger.warning("Rejected invalid session_id: %r", session_id)
        raise HTTPException(
            status_code=400, detail="Invalid session ID format"
        )
    return session_id


def validate_file_extension(filename: str) -> str:
    """Validate uploaded file has an allowed extension, or raise 400."""
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in cfg.ALLOWED_EXTENSIONS:
        logger.warning(
            "Rejected file with disallowed extension: %r", filename
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{ext}' not allowed. "
                f"Allowed: {', '.join(sorted(cfg.ALLOWED_EXTENSIONS))}"
            ),
        )
    return filename


# --------------- Error Helpers ---------------


def safe_error_response(
    exc: Exception, context: str = "operation", status_code: int = 500
):
    """
    Log the real exception but return a sanitized message to the client.
    In development mode, the real error is included for debugging.
    """
    logger.error("Error in %s: %s", context, exc, exc_info=True)
    if cfg.ENVIRONMENT == "development":
        detail = f"[DEV] {context}: {exc}"
    else:
        detail = (
            f"An internal error occurred during {context}. "
            "Please try again later."
        )
    raise HTTPException(status_code=status_code, detail=detail)


# --------------- Admin Auth ---------------


def require_admin_key(request: Request):
    """
    Dependency that checks for a valid X-Admin-Key header.
    Raises 403 if missing or incorrect.
    """
    provided_key = request.headers.get("X-Admin-Key", "")
    if not provided_key or provided_key != cfg.ADMIN_API_KEY:
        logger.warning(
            "Unauthorized admin access attempt from %s",
            request.client.host,
        )
        raise HTTPException(
            status_code=403, detail="Forbidden: invalid admin key"
        )
