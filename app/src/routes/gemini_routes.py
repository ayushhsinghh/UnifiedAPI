"""Gemini translation submission, capabilities, and owned artifact helpers."""
import asyncio
import logging
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from commons import limiter
from configs.config import get_config
from security import validate_file_extension, validate_job_id
from src.auth.tokens import get_current_user
from src.database.job_repository import get_job
from src.database import gemini_jobs_repository as repo
from src.transcription.gemini_languages import LANGUAGES, whisper_language
from src.transcription.gemini_media import MediaError, probe, require_space
from src.transcription.gemini_worker import cleanup, safe_artifact
from src.transcription.gemini_logging import context, event, failure

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/gemini', tags=['gemini-translation'])


@router.get('/capabilities')
@limiter.limit('30/minute')
def capabilities(request: Request):
    cfg = get_config()
    return {'enabled': cfg.GEMINI_TRANSLATION_ENABLED and bool(cfg.GEMINI_API_KEY),
            'model': cfg.GEMINI_TRANSLATION_MODEL, 'max_upload_bytes': cfg.MAX_UPLOAD_SIZE,
            'max_duration_seconds': cfg.GEMINI_TRANSLATION_MAX_DURATION_SECONDS,
            'languages': [{'code': code, 'name': name, 'subtitle_fallback_supported': whisper_language(code) is not None}
                          for code, name in LANGUAGES.items()]}


@router.post('/jobs', status_code=202)
@limiter.limit('2/hour')
async def create_gemini_job(request: Request, file: UploadFile = File(...),
                           target_language: str = Form(...), generate_subtitles: bool = Form(True),
                           current_user: dict = Depends(get_current_user)):
    cfg = get_config()
    if not cfg.GEMINI_TRANSLATION_ENABLED or not cfg.GEMINI_API_KEY:
        event(logger, 'upload_unavailable', level=logging.WARNING,
              enabled=cfg.GEMINI_TRANSLATION_ENABLED, api_key_present=bool(cfg.GEMINI_API_KEY))
        raise HTTPException(503, 'Gemini audio translation is not enabled on this server.')
    if target_language not in LANGUAGES:
        event(logger, 'upload_invalid_language', level=logging.WARNING)
        raise HTTPException(422, 'Select a supported Gemini target language.')
    original = Path((file.filename or '').replace('\\', '/')).name
    validate_file_extension(original)
    job_id = 'job_' + uuid4().hex
    directory = Path(cfg.UPLOAD_DIR)
    # The original filename is display metadata, never part of a filesystem path.
    stored_name = job_id + '_source' + Path(original).suffix.lower()
    destination = directory / stored_name
    partial = destination.with_suffix(destination.suffix + '.part')
    log_token = context.set({'job': job_id, 'stage': 'upload'})
    try:
        event(logger, 'upload_started', target_language=target_language, generate_subtitles=generate_subtitles)
        directory.mkdir(parents=True, exist_ok=True)
        total = 0
        with partial.open('wb') as output:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > cfg.MAX_UPLOAD_SIZE:
                    raise HTTPException(413, 'The maximum upload size is 6 GB.')
                await asyncio.to_thread(require_space, directory, len(chunk))
                await asyncio.to_thread(output.write, chunk)
        if not total:
            raise HTTPException(422, 'The uploaded video is empty.')
        event(logger, 'upload_saved', bytes=total)
        event(logger, 'upload_probe_started')
        info = await probe(partial, cfg.GEMINI_TRANSLATION_MAX_DURATION_SECONDS)
        event(logger, 'upload_probe_completed', duration_seconds=info['duration_seconds'],
              audio_offset_seconds=info['audio_offset_seconds'])
        output_dir = Path(cfg.OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(require_space, output_dir,
                                info['input_samples'] * 2 + info['output_samples'] * 2 * 5)
        os.replace(partial, destination)
        await asyncio.to_thread(repo.enqueue, job_id, current_user['email'], {
            'video': stored_name, 'original_filename': original,
            'model': cfg.GEMINI_TRANSLATION_MODEL, 'target_language': target_language,
            'generate_subtitles': generate_subtitles, 'translate': True, 'language': None,
            'media_info': info, 'source_duration_seconds': info['duration_seconds']})
    except MediaError as exc:
        failure(logger, 'upload_validation_failed', exc)
        partial.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise HTTPException(422, str(exc)) from None
    except BaseException as exc:
        if isinstance(exc, asyncio.CancelledError):
            event(logger, 'upload_cancelled', level=logging.WARNING)
        elif isinstance(exc, HTTPException):
            event(logger, 'upload_rejected', level=logging.WARNING, status_code=exc.status_code, reason=exc.detail)
        else:
            failure(logger, 'upload_failed', exc)
        partial.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    finally:
        context.reset(log_token)
        await file.close()
    logger.info('Gemini upload accepted and queued: job=%s bytes=%d duration_seconds=%.3f',
                job_id, total, info['duration_seconds'])
    return {'job_id': job_id, 'status': 'pending', 'engine': repo.ENGINE}


def owned(job_id, user):
    validate_job_id(job_id)
    job = get_job(job_id, user_email=user['email'])
    if not job:
        raise HTTPException(404, 'Job not found')
    return job


def artifact_response(job, kind, request):
    value = job.get('artifacts', {}).get(kind)
    if not value:
        raise HTTPException(404, 'This artifact is not ready.')
    try:
        path = safe_artifact(job['job_id'], value)
    except MediaError:
        raise HTTPException(404, 'Artifact unavailable.') from None
    if not path.is_file():
        raise HTTPException(404, 'Artifact unavailable.')
    name = Path(job.get('original_filename', 'video')).stem
    types = {'wav': 'audio/wav', 'mp3': 'audio/mpeg', 'srt': 'application/x-subrip', 'vtt': 'text/vtt'}
    # Starlette FileResponse supports bounded streaming, conditional and range requests.
    return FileResponse(path, media_type=types[kind], filename=f'{name}.{job["target_language"]}.{kind}',
                        headers={'Cache-Control': 'private, no-store'})


async def cancel_owned(job_id, user, delete=False):
    job = owned(job_id, user)
    if job.get('engine') != repo.ENGINE:
        raise HTTPException(409, 'This action is supported only for Gemini translation jobs.')
    doc = await asyncio.to_thread(repo.request_cancel, job_id, user['email'], delete)
    if not doc:
        raise HTTPException(404, 'Job not found')
    event(logger, 'job_cancellation_requested', job=job_id, status=doc['status'], delete_requested=delete)
    if doc['status'] != 'running' and delete:
        await asyncio.to_thread(cleanup, doc)
    return {'job_id': job_id, 'status': 'cancelling' if doc['status'] == 'running' else 'cancelled',
            'delete_requested': delete}
