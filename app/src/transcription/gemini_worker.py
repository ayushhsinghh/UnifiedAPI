"""Run from app/: python -m src.transcription.gemini_worker [--once]."""
import argparse
import asyncio
import array
import json
import logging
import os
import shutil
import sys
import wave
from pathlib import Path
from uuid import uuid4

from configs.config import get_config
from src.database import gemini_jobs_repository as repo
from . import gemini_media as media
from .gemini_languages import whisper_language
from .gemini_live import translate_section

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
    shutil.rmtree(job_directory(job['job_id']).parent, ignore_errors=True)
    # Only this flow's UUID-named upload belongs to this operation.
    upload = Path(get_config().UPLOAD_DIR) / job['video']
    if upload.name.startswith(job['job_id'] + '_'):
        upload.unlink(missing_ok=True)
    repo.collection().delete_one({'job_id': job['job_id'], 'engine': repo.ENGINE,
                                   'delete_requested': True, 'status': {'$ne': 'running'}})


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
        return transcripts
    code = whisper_language(language)
    if not code:
        raise media.MediaError('Subtitle timing is unavailable for this target language. Audio is ready; retry subtitles later.')
    from .worker import get_model
    model = get_model(get_config().GEMINI_TRANSLATION_SUBTITLE_MODEL)
    segments, _ = model.transcribe(str(raw), language=code, vad_filter=True, beam_size=5)
    cues = [{'start': segment.start, 'end': segment.end, 'text': segment.text.strip()}
            for segment in segments if segment.text.strip()]
    if not cues or not media.valid_cues(cues, duration):
        raise media.MediaError('Reliable subtitle timing could not be produced. The translated audio remains available.')
    return cues


async def process(job, translator=translate_section):
    cfg = get_config()
    job_id, token = job['job_id'], job['lease_token']
    root = job_directory(job_id)
    attempt = root / token
    attempt.mkdir(parents=True, exist_ok=True)

    async def update(**fields):
        await asyncio.to_thread(repo.update, job_id, token, **fields)

    async def check():
        return await asyncio.to_thread(repo.check, job_id, token)

    if job.get('delete_requested') or job.get('cancel_requested'):
        raise repo.JobCancelled()
    await update(stage='extraction')
    info = job.get('media_info')
    if not info:
        info = await media.probe(Path(cfg.UPLOAD_DIR) / job['video'], cfg.GEMINI_TRANSLATION_MAX_DURATION_SECONDS)
    await asyncio.to_thread(media.require_space, root, info['output_samples'] * 2 * 5 + info['input_samples'] * 2)
    source = attempt / 'source.wav'
    old_source = job.get('source_audio')
    if old_source and safe_artifact(job_id, old_source).is_file():
        source = safe_artifact(job_id, old_source)
    else:
        await media.extract(Path(cfg.UPLOAD_DIR) / job['video'], source, info)
    await update(source_audio=str(source), media_info=info, source_duration_seconds=info['duration_seconds'])
    boundaries = await asyncio.to_thread(lambda: list(media.sections(source)))
    await update(total_segments=len(boundaries))
    completed = list(job.get('sections', []))
    # Invariant: checkpoints must be a contiguous prefix, with durable validated files.
    for index, section in enumerate(completed):
        if index >= len(boundaries) or (section['start_sample'], section['end_sample']) != boundaries[index]:
            raise media.MediaError('Translation checkpoint does not match this source.')
        if media.wav_samples(safe_artifact(job_id, section['fitted'])) != section['fit']['target_samples']:
            raise media.MediaError('Translation checkpoint audio is missing or damaged.')
    warnings = list(job.get('warnings', []))
    for index in range(len(completed), len(boundaries)):
        await check()
        start, end = boundaries[index]
        await update(stage='translation')
        raw = attempt / f'{index:05d}-raw.wav'
        fitted = attempt / f'{index:05d}-fitted.wav'
        no_speech = await asyncio.to_thread(silent_section, source, start, end)
        result = {'transcripts': [], 'input_transcript': ''}
        if no_speech:
            await asyncio.to_thread(media.write_pcm, raw, b'\0\0')
        else:
            for retry_index in range(3):
                await check()
                try:
                    raw.unlink(missing_ok=True)
                    result = await translator(source, start, end, job['target_language'], raw,
                                              cfg.GEMINI_API_KEY, cfg.GEMINI_TRANSLATION_MODEL)
                    break
                except (repo.JobCancelled, repo.LeaseLost, asyncio.CancelledError):
                    raise
                except Exception:
                    raw.unlink(missing_ok=True)
                    if retry_index == 2:
                        raise media.MediaError('Translation failed after three attempts. Retry resumes from the last completed section.') from None
                    logger.warning('Retrying Gemini section %s for job %s', index, job_id)
                    await asyncio.sleep((2, 5)[retry_index])
        await check()
        await update(stage='timing')
        start_out = round(start * media.OUT_RATE / media.IN_RATE)
        end_out = info['output_samples'] if index == len(boundaries) - 1 else round(end * media.OUT_RATE / media.IN_RATE)
        fit = await media.fit_audio(raw, fitted, end_out - start_out)
        if fit['speed_ratio'] > 1.5:
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
        completed.append(section)
        await update(warnings=warnings)

    await check()
    await update(stage='assembly')
    artifacts = dict(job.get('artifacts', {}))
    wav = attempt / 'translated.wav'
    if artifacts.get('wav') and safe_artifact(job_id, artifacts['wav']).is_file():
        wav = safe_artifact(job_id, artifacts['wav'])
        if media.wav_samples(wav) != info['output_samples']:
            raise media.MediaError('Saved master audio failed duration validation.')
    else:
        await asyncio.to_thread(media.concatenate, [safe_artifact(job_id, s['fitted']) for s in completed], wav, info['output_samples'])
    artifacts['wav'] = str(wav)
    await update(artifacts=artifacts)
    mp3 = attempt / 'translated.mp3'
    if not (artifacts.get('mp3') and safe_artifact(job_id, artifacts['mp3']).is_file()):
        await media.command('ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', wav, '-c:a', 'libmp3lame', '-b:a', '128k', mp3)
        if mp3.stat().st_size <= 0:
            raise media.MediaError('MP3 conversion failed.')
        artifacts['mp3'] = str(mp3)
        await update(artifacts=artifacts)
    if job.get('generate_subtitles'):
        await update(stage='subtitles')
        cues = []
        for section in completed:
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
    await check()
    await update(artifacts=artifacts, status='done', stage='completed', progress_percentage=100, error=None)


async def run_claimed(job, translator=translate_section):
    job_id, token = job['job_id'], job['lease_token']
    async def guard():
        elapsed = 0
        while True:
            await asyncio.sleep(1)
            await asyncio.to_thread(repo.check, job_id, token)
            elapsed += 1
            if elapsed >= get_config().GEMINI_TRANSLATION_HEARTBEAT_SECONDS:
                await asyncio.to_thread(repo.heartbeat, job_id, token)
                elapsed = 0
    work, watch = asyncio.create_task(process(job, translator)), asyncio.create_task(guard())
    try:
        done, _ = await asyncio.wait((work, watch), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    except repo.JobCancelled:
        work.cancel()
        await asyncio.gather(work, return_exceptions=True)
        cancelled = await asyncio.to_thread(repo.finish_cancel, job_id, token)
        if cancelled and cancelled.get('delete_requested'):
            await asyncio.to_thread(cleanup, cancelled)
    except repo.LeaseLost:
        logger.warning('Translation lease lost for %s; this worker stops.', job_id)
    except asyncio.CancelledError:
        raise  # Leave lease/checkpoints for recovery; do not publish a false failure.
    except Exception as exc:
        message = str(exc) if isinstance(exc, media.MediaError) else 'Translation processing failed. Retry resumes saved sections.'
        logger.error('Translation job %s failed (%s).', job_id, type(exc).__name__)
        try:
            await asyncio.to_thread(repo.update, job_id, token, status='failed', stage='failed', error=message)
        except repo.JobCancelled:
            cancelled = await asyncio.to_thread(repo.finish_cancel, job_id, token)
            if cancelled and cancelled.get('delete_requested'):
                await asyncio.to_thread(cleanup, cancelled)
        except repo.LeaseLost:
            pass
    finally:
        work.cancel()
        watch.cancel()
        await asyncio.gather(work, watch, return_exceptions=True)


async def main(once=False):
    cfg = get_config()
    if not cfg.GEMINI_TRANSLATION_ENABLED or not cfg.GEMINI_API_KEY:
        raise SystemExit('Enable GEMINI_TRANSLATION_ENABLED and configure GEMINI_API_KEY before starting the worker.')
    while True:
        job = await asyncio.to_thread(repo.claim)
        if job:
            await run_claimed(job)
        elif once:
            return
        else:
            await asyncio.sleep(3)
        if once:
            return


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main(parser.parse_args().once))
