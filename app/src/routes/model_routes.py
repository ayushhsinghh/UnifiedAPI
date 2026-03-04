"""
Model file API routes.

All endpoints require a valid ``X-Api-Key`` header.

Endpoints:
    GET    /api/models                    — list available models
    GET    /api/models/download/{model_id} — stream / download a model file
"""

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from commons import limiter
from configs.config import get_config
from security import require_models_api_key

logger = logging.getLogger(__name__)

cfg = get_config()

router = APIRouter(prefix="/api", tags=["models"])

# ── Response schema ──────────────────────────────────────────────────────


class ModelInfo(BaseModel):
    """Schema for a single model entry."""

    id: str
    name: str
    fileName: str
    downloadUrl: str
    sizeBytes: int
    lastModified: str
    checksum: str


# ── Helpers ──────────────────────────────────────────────────────────────

# Cache checksum results so we only hash each file once per process
_checksum_cache: dict[str, str] = {}


def _model_id(filename: str) -> str:
    """Derive a stable, URL-safe short ID from the filename."""
    return hashlib.sha256(filename.encode()).hexdigest()[:12]


def _file_checksum(filepath: str) -> str:
    """Return the SHA-256 hex digest for *filepath*, with caching."""
    if filepath in _checksum_cache:
        return _checksum_cache[filepath]
    sha = hashlib.sha256()
    with open(filepath, "rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            sha.update(chunk)
    digest = sha.hexdigest()
    _checksum_cache[filepath] = digest
    return digest


def _human_name(filename: str) -> str:
    """Turn a filename like 'Gemma3-1B-IT_multi-prefill-seq_q4_ekv2048.task'
    into 'Gemma3 1B IT multi prefill seq q4 ekv2048'."""
    stem = os.path.splitext(filename)[0]
    return stem.replace("_", " ").replace("-", " ")


def _scan_models() -> List[ModelInfo]:
    """Scan the models directory and return metadata for every file."""
    models_dir = cfg.MODELS_DIR
    if not os.path.isdir(models_dir):
        logger.warning("Models directory does not exist: %s", models_dir)
        return []

    results: list[ModelInfo] = []
    for entry in sorted(os.listdir(models_dir)):
        full_path = os.path.join(models_dir, entry)
        if not os.path.isfile(full_path):
            continue

        stat = os.stat(full_path)
        mid = _model_id(entry)
        results.append(
            ModelInfo(
                id=mid,
                name=_human_name(entry),
                fileName=entry,
                downloadUrl=f"/api/models/download/{mid}",
                sizeBytes=stat.st_size,
                lastModified=datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                checksum=_file_checksum(full_path),
            )
        )
    return results


def _find_model_by_id(model_id: str) -> tuple[ModelInfo, str] | None:
    """Return (ModelInfo, absolute_path) for *model_id*, or None."""
    models_dir = cfg.MODELS_DIR
    if not os.path.isdir(models_dir):
        return None
    for entry in os.listdir(models_dir):
        full_path = os.path.join(models_dir, entry)
        if os.path.isfile(full_path) and _model_id(entry) == model_id:
            stat = os.stat(full_path)
            mid = _model_id(entry)
            info = ModelInfo(
                id=mid,
                name=_human_name(entry),
                fileName=entry,
                downloadUrl=f"/api/models/download/{mid}",
                sizeBytes=stat.st_size,
                lastModified=datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
                checksum=_file_checksum(full_path),
            )
            return info, full_path
    return None


# ── Endpoints ────────────────────────────────────────────────────────────


@router.get("/models", response_model=list[ModelInfo])
@limiter.limit("2/minute")
async def list_models(
    request: Request, _=Depends(require_models_api_key)
) -> list[ModelInfo]:
    """Return metadata for every model file in the models directory."""
    return _scan_models()


@router.get("/models/download/{model_id}")
@limiter.limit("5/hour")
async def download_model(
    request: Request, model_id: str, _=Depends(require_models_api_key)
):
    """Stream a model file as a binary download."""
    result = _find_model_by_id(model_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Model not found")
    info, filepath = result
    return FileResponse(
        path=filepath,
        filename=info.fileName,
        media_type="application/octet-stream",
    )
