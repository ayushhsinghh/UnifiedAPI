"""Run from app/: python -m src.transcription.gemini_worker [--once]."""
import argparse
import asyncio
import array
import json
import logging
import os
import shutil
import sys
import time
import wave
from pathlib import Path
from uuid import uuid4

from configs.config import get_config
from src.database import gemini_jobs_repository as repo
from . import gemini_media as media
from .gemini_languages import whisper_language
from .gemini_live import translate_section
from .gemini_logging import context, event, failure

logger = logging.getLogger(__name__)


def job_directory(job_id):
    return Path(get_config().OUTPUT_DIR) / job_id / 'gemini'


def safe_artifact(job_id, value):
    root = job_directory(job_id).resolve()
    path = Path(value).resolve()
    if not path.is_relative_to(root):
        raise media.MediaError('Invalid translation artifact path.')
    return path


def cleanup(job):
    event(logger, 'cleanup_started', job=job['job_id'])
    shutil.rmtree(job_directory(job['job_id']).parent, ignore_errors=True)
    # Only this flow's UUID-named upload belongs to this operation.
    upload = Path(get_config().UPLOAD_DIR) / job['video']
    if upload.name.startswith(job['job_id'] + '_'):
        upload.unlink(missing_ok=True)
    repo.collection().delete_one({'job_id': job['job_id'], 'engine': repo.ENGINE,
                                   'delete_requested': True, 'status': {'$ne': 'running'}})
    event(logger, 'cleanup_completed', job=job['job_id'])


def silent_section(source, start, end):
    with wave.open(str(source), 'rb') as audio:
        audio.setpos(start)
        remaining = end - start
        while remaining:
            size = min(remaining, 65536)
            samples = array.array('h', audio.readframes(size))
            if sys.byteorder != 'little':
                samples.byteswap()
            if samples and max(map(abs, samples)) > 0:
                return False
            remaining -= size
    return True


def align_subtitles(raw, transcripts, language):
    """Use actual output offsets, otherwise ASR on generated audio; never estimate text timing."""
    duration = media.wav_samples(raw) / media.OUT_RATE
    if transcripts and media.valid_cues(transcripts, duration):
        event(logger, 'subtitle_timing_provider_offsets', cues=len(transcripts))
        return transcripts
    code = whisper_language(language)
    if not code:
        raise media.MediaError('Subtitle timing is unavailable for this target language. Audio is ready; retry subtitles later.')
    from .worker import get_model
    event(logger, 'subtitle_timing_whisper_started', language=code,
          model=get_config().GEMINI_TRANSLATION_SUBTITLE_MODEL)
    model = get_model(get_config().GEMINI_TRANSLATION_SUBTITLE_MODEL)
    segments, _ = model.transcribe(str(raw), language=code, vad_filter=True, beam_size=5)
    cues = [{'start': segment.start, 'end': segment.end, 'text': segment.text.strip()}
            for segment in segments if segment.text.strip()]
    if not cues or not media.valid_cues(cues, duration):
        raise media.MediaError('Reliable subtitle timing could not be produced. The translated audio remains available.')
    event(logger, 'subtitle_timing_whisper_completed', cues=len(cues))
    return cues


async def process(job, translator=translate_section):
    try:
        return await _process(job, translator)
    except (repo.JobCancelled, repo.LeaseLost, asyncio.CancelledError):
        raise
    except Exception as exc:
        failure(logger, 'processing_failed', exc)
        raise


async def _process(job, translator):
    cfg = get_config()
    job_id, token = job['job_id'], job['lease_token']
    root = job_directory(job_id)
    attempt = root / token
    attempt.mkdir(parents=True, exist_ok=True)

    async def update(**fields):
        await asyncio.to_thread(repo.update, job_id, token, **fields)
        if 'stage' in fields:
            context.set(dict(context.get(), stage=fields['stage']))
            event(logger, 'stage_started', **{k: v for k, v in fields.items() if k in ('stage', 'status')})

    async def check():
        return await asyncio.to_thread(repo.check, job_id, token)

    if job.get('delete_requested') or job.get('cancel_requested'):
        raise repo.JobCancelled()
    await update(stage='extraction')
    info = job.get('media_info')
    if not info:
        event(logger, 'media_probe_started')
        info = await media.probe(Path(cfg.UPLOAD_DIR) / job['video'], cfg.GEMINI_TRANSLATION_MAX_DURATION_SECONDS)
    event(logger, 'media_validated', duration_seconds=info['duration_seconds'],
          input_samples=info['input_samples'], output_samples=info['output_samples'],
          audio_offset_seconds=info.get('audio_offset_seconds', 0))
    await asyncio.to_thread(media.require_space, root, info['output_samples'] * 2 * 5 + info['input_samples'] * 2)
    source = attempt / 'source.wav'
    old_source = job.get('source_audio')
    if old_source and safe_artifact(job_id, old_source).is_file():
        source = safe_artifact(job_id, old_source)
        event(logger, 'extraction_checkpoint_reused')
    else:
        event(logger, 'extraction_started')
        await media.extract(Path(cfg.UPLOAD_DIR) / job['video'], source, info)
        event(logger, 'extraction_completed')
    await update(source_audio=str(source), media_info=info, source_duration_seconds=info['duration_seconds'])
    boundaries = await asyncio.to_thread(lambda: list(media.sections(source)))
    event(logger, 'sections_prepared', total_sections=len(boundaries), completed_sections=len(job.get('sections', [])))
    await update(total_segments=len(boundaries))
    completed = list(job.get('sections', []))
    # Invariant: checkpoints must be a contiguous prefix, with durable validated files.
    for index, section in enumerate(completed):
        context.set(dict(context.get(), section=index + 1))
        if index >= len(boundaries) or (section['start_sample'], section['end_sample']) != boundaries[index]:
            raise media.MediaError('Translation checkpoint does not match this source.')
        if media.wav_samples(safe_artifact(job_id, section['fitted'])) != section['fit']['target_samples']:
            raise media.MediaError('Translation checkpoint audio is missing or damaged.')
        event(logger, 'section_checkpoint_validated')
    warnings = list(job.get('warnings', []))
    for index in range(len(completed), len(boundaries)):
        context.set(dict(context.get(), section=index + 1, attempt=0))
        await check()
        start, end = boundaries[index]
        event(logger, 'section_started', total_sections=len(boundaries),
              start_seconds=start / media.IN_RATE, duration_seconds=(end - start) / media.IN_RATE)
        await update(stage='translation')
        raw = attempt / f'{index:05d}-raw.wav'
        fitted = attempt / f'{index:05d}-fitted.wav'
        no_speech = await asyncio.to_thread(silent_section, source, start, end)
        result = {'transcripts': [], 'input_transcript': ''}
        if no_speech:
            event(logger, 'section_silent_skipping_provider')
            await asyncio.to_thread(media.write_pcm, raw, b'\0\0')
        else:
            for retry_index in range(3):
                context.set(dict(context.get(), attempt=retry_index + 1))
                await check()
                started = time.monotonic()
                try:
                    event(logger, 'translation_attempt_started', max_attempts=3)
                    raw.unlink(missing_ok=True)
                    result = await translator(source, start, end, job['target_language'], raw,
                                              cfg.GEMINI_API_KEY, cfg.GEMINI_TRANSLATION_MODEL)
                    event(logger, 'translation_attempt_completed', elapsed_seconds=round(time.monotonic() - started, 3))
                    break
                except (repo.JobCancelled, repo.LeaseLost, asyncio.CancelledError):
                    raise
                except Exception as exc:
                    failure(logger, 'translation_attempt_failed', exc,
                            elapsed_seconds=round(time.monotonic() - started, 3))
                    raw.unlink(missing_ok=True)
                    if retry_index == 2:
                        raise media.MediaError('Translation failed after three attempts. Retry resumes from the last completed section.') from exc
                    event(logger, 'translation_retry_scheduled', level=logging.WARNING,
                          delay_seconds=(2, 5)[retry_index])
                    await asyncio.sleep((2, 5)[retry_index])
        await check()
        await update(stage='timing')
        start_out = round(start * media.OUT_RATE / media.IN_RATE)
        end_out = info['output_samples'] if index == len(boundaries) - 1 else round(end * media.OUT_RATE / media.IN_RATE)
        fit = await media.fit_audio(raw, fitted, end_out - start_out)
        event(logger, 'timing_completed', **fit)
        if fit['speed_ratio'] > 1.5:
            event(logger, 'high_speech_compression', level=logging.WARNING, speed_ratio=fit['speed_ratio'])
            warnings.append(f'Section {index + 1} speech compressed to {fit["speed_ratio"]:.2f}x to preserve video duration.')
        section = {'index': index, 'start_sample': start, 'end_sample': end,
                   'raw': str(raw), 'fitted': str(fitted), 'fit': fit, 'silent': no_speech,
                   'transcripts': result['transcripts']}
        # Transcripts are committed with the audio; never reuse an incomplete provider attempt.
        manifest = attempt / f'{index:05d}.json'
        temp = manifest.with_suffix('.part')
        temp.write_text(json.dumps(section), encoding='utf-8')
        os.replace(temp, manifest)
        await asyncio.to_thread(repo.checkpoint, job_id, token, section, info['input_samples'])
        event(logger, 'section_checkpoint_saved', processed_duration_seconds=end / media.IN_RATE)
        completed.append(section)
        await update(warnings=warnings)

    context.set(dict(context.get(), section='all', attempt=0))
    await check()
    await update(stage='assembly')
    artifacts = dict(job.get('artifacts', {}))
    wav = attempt / 'translated.wav'
    if artifacts.get('wav') and safe_artifact(job_id, artifacts['wav']).is_file():
        event(logger, 'wav_checkpoint_reused')
        wav = safe_artifact(job_id, artifacts['wav'])
        if media.wav_samples(wav) != info['output_samples']:
            raise media.MediaError('Saved master audio failed duration validation.')
    else:
        event(logger, 'wav_assembly_started', sections=len(completed))
        await asyncio.to_thread(media.concatenate, [safe_artifact(job_id, s['fitted']) for s in completed], wav, info['output_samples'])
    artifacts['wav'] = str(wav)
    await update(artifacts=artifacts)
    event(logger, 'wav_ready', samples=info['output_samples'])
    mp3 = attempt / 'translated.mp3'
    if not (artifacts.get('mp3') and safe_artifact(job_id, artifacts['mp3']).is_file()):
        event(logger, 'mp3_encoding_started')
        await media.command('ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', wav, '-c:a', 'libmp3lame', '-b:a', '128k', mp3)
        if mp3.stat().st_size <= 0:
            raise media.MediaError('MP3 conversion failed.')
        artifacts['mp3'] = str(mp3)
        await update(artifacts=artifacts)
    event(logger, 'mp3_ready')
    if job.get('generate_subtitles'):
        await update(stage='subtitles')
        cues = []
        for section in completed:
            context.set(dict(context.get(), section=section['index'] + 1))
            await check()
            if section['silent']:
                continue
            raw = safe_artifact(job_id, section['raw'])
            aligned = await asyncio.to_thread(align_subtitles, raw, section['transcripts'], job['target_language'])
            origin = round(section['start_sample'] * 1.5) / media.OUT_RATE
            # Use actual compressed speech length for the timestamp map, not padded silence.
            scale = section['fit']['speech_samples'] / section['fit']['raw_samples']
            limit = section['fit']['target_samples'] / media.OUT_RATE
            for cue in aligned:
                cues.append({'start': origin + min(cue['start'] * scale, limit),
                             'end': origin + min(cue['end'] * scale, limit), 'text': cue['text']})
        srt, vtt = attempt / 'translated.srt', attempt / 'translated.vtt'
        await asyncio.to_thread(media.write_subtitles, cues, srt, vtt, info['duration_seconds'])
        artifacts.update(srt=str(srt), vtt=str(vtt))
        event(logger, 'subtitles_validated', cues=len(cues), formats='srt,vtt')
    await check()
    await update(artifacts=artifacts, status='done', stage='completed', progress_percentage=100, error=None)
    event(logger, 'job_completed', artifacts=','.join(sorted(artifacts)))


async def run_claimed(job, translator=translate_section):
    job_id, token = job['job_id'], job['lease_token']
    log_token = context.set({'job': job_id, 'stage': 'worker'})
    started = time.monotonic()
    event(logger, 'job_claimed', model=job.get('model', get_config().GEMINI_TRANSLATION_MODEL),
          target_language=job['target_language'], completed_sections=len(job.get('sections', [])),
          generate_subtitles=job.get('generate_subtitles', False))
    async def guard():
        elapsed = 0
        while True:
            await asyncio.sleep(1)
            await asyncio.to_thread(repo.check, job_id, token)
            elapsed += 1
            if elapsed >= get_config().GEMINI_TRANSLATION_HEARTBEAT_SECONDS:
                await asyncio.to_thread(repo.heartbeat, job_id, token)
                event(logger, 'heartbeat', elapsed_seconds=round(time.monotonic() - started),
                      lease_seconds=get_config().GEMINI_TRANSLATION_LEASE_SECONDS)
                elapsed = 0
    work, watch = asyncio.create_task(process(job, translator)), asyncio.create_task(guard())
    try:
        done, _ = await asyncio.wait((work, watch), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except repo.JobCancelled:
        event(logger, 'job_cancellation_received', level=logging.WARNING)
        work.cancel()
        await asyncio.gather(work, return_exceptions=True)
        cancelled = await asyncio.to_thread(repo.finish_cancel, job_id, token)
        if cancelled and cancelled.get('delete_requested'):
            await asyncio.to_thread(cleanup, cancelled)
    except repo.LeaseLost as exc:
        event(logger, 'job_lease_lost', level=logging.WARNING, reason=str(exc))
    except asyncio.CancelledError:
        event(logger, 'worker_stopping_job_retained', level=logging.WARNING)
        raise  # Leave lease/checkpoints for recovery; do not publish a false failure.
    except Exception as exc:
        message = str(exc) if isinstance(exc, media.MediaError) else 'Translation processing failed. Retry resumes saved sections.'
        failure(logger, 'job_failed', exc, elapsed_seconds=round(time.monotonic() - started, 3))
        try:
            await asyncio.to_thread(repo.update, job_id, token, status='failed', stage='failed', error=message)
            event(logger, 'job_failure_saved')
        except repo.JobCancelled:
            cancelled = await asyncio.to_thread(repo.finish_cancel, job_id, token)
            if cancelled and cancelled.get('delete_requested'):
                await asyncio.to_thread(cleanup, cancelled)
        except repo.LeaseLost:
            event(logger, 'job_failure_not_saved_lease_lost', level=logging.WARNING)
        except Exception as save_exc:
            failure(logger, 'job_failure_save_failed', save_exc)
    finally:
        work.cancel()
        watch.cancel()
        await asyncio.gather(work, watch, return_exceptions=True)
        context.reset(log_token)


async def main(once=False):
    cfg = get_config()
    if not cfg.GEMINI_TRANSLATION_ENABLED or not cfg.GEMINI_API_KEY:
        event(logger, 'worker_configuration_invalid', level=logging.ERROR,
              enabled=cfg.GEMINI_TRANSLATION_ENABLED, api_key_present=bool(cfg.GEMINI_API_KEY))
        raise SystemExit('Enable GEMINI_TRANSLATION_ENABLED and configure GEMINI_API_KEY before starting the worker.')
    event(logger, 'worker_ready', pid=os.getpid(), model=cfg.GEMINI_TRANSLATION_MODEL,
          heartbeat_seconds=cfg.GEMINI_TRANSLATION_HEARTBEAT_SECONDS,
          lease_seconds=cfg.GEMINI_TRANSLATION_LEASE_SECONDS)
    while True:
        try:
            job = await asyncio.to_thread(repo.claim)
        except Exception as exc:
            failure(logger, 'queue_claim_failed', exc)
            raise
        if job:
            try:
                await run_claimed(job)
            except asyncio.CancelledError:
                event(logger, 'worker_shutdown', job=job['job_id'])
                raise
            except Exception as exc:
                failure(logger, 'worker_dispatch_failed', exc, job=job['job_id'])
                raise
        elif once:
            return
        else:
            await asyncio.sleep(3)
        if once:
            return


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    from logging_config import setup_logging
    setup_logging(forward_to_parent=os.getenv('SUBFORGE_GEMINI_LOG_FORWARDING') == '1')
    # Protocol DEBUG logs can contain audio frames, transcripts, and auth headers.
    # The worker's own events provide diagnostics without these payloads.
    for noisy_logger in ('websockets', 'httpx', 'httpcore', 'google', 'google_genai'):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
    asyncio.run(main(parser.parse_args().once))
