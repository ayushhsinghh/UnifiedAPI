"""Offline queue, media, SDK protocol, and authenticated route regressions.

Run in an environment with requirements.txt plus mongomock:
    python -m unittest discover -s tests -p 'test_gemini_translation.py' -v
No live credentials, MongoDB server or model download is used.
"""
import asyncio
import array
import importlib
import json
import math
import os
import shutil
import struct
import sys
import tempfile
import types
import unittest
import wave
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

APP = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(APP))

from src.transcription import gemini_media as media
from src.transcription import gemini_languages as languages
from src.transcription.gemini_live import translate_section


def cfg(root):
    return types.SimpleNamespace(UPLOAD_DIR=str(root / 'uploads'), OUTPUT_DIR=str(root / 'outputs'),
        JOBS_COLLECTION='jobs', MAX_UPLOAD_SIZE=6 * 1024**3, GEMINI_TRANSLATION_ENABLED=True,
        GEMINI_TRANSLATION_MODEL='gemini-3.5-live-translate-preview', GEMINI_API_KEY='test-only-key',
        GEMINI_TRANSLATION_MAX_DURATION_SECONDS=21600, GEMINI_TRANSLATION_LEASE_SECONDS=180,
        GEMINI_TRANSLATION_HEARTBEAT_SECONDS=30, GEMINI_TRANSLATION_SUBTITLE_MODEL='medium')


def tone(path, seconds=1, rate=24000, amplitude=1000):
    data = array.array('h', (int(amplitude * math.sin(2 * math.pi * 220 * i / rate)) for i in range(round(seconds * rate))))
    if sys.byteorder != 'little':
        data.byteswap()
    media.write_pcm(path, data.tobytes(), rate)


class MediaTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    async def test_compression_and_padding_have_exact_sample_counts(self):
        for seconds, target in ((.25, 24000), (1.7, 24000), (5, 12000)):
            raw, fitted = self.root / 'raw.wav', self.root / 'fit.wav'
            tone(raw, seconds)
            fit = await media.fit_audio(raw, fitted, target)
            self.assertEqual(media.wav_samples(fitted), target)
            self.assertLessEqual(fit['speech_samples'], target)
            self.assertGreaterEqual(fit['speed_ratio'], 1)
            if seconds < 1:
                self.assertEqual(fit['speed_ratio'], 1)
                with wave.open(str(fitted), 'rb') as audio:
                    audio.setpos(fit['speech_samples'])
                    self.assertFalse(any(audio.readframes(target)))

    async def test_extract_respects_video_offset(self):
        video = self.root / 'offset.mkv'
        await media.command('ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=size=32x32:rate=10:duration=2',
            '-itsoffset', '0.5', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=16000:duration=1',
            '-c:v', 'libx264', '-c:a', 'pcm_s16le', video)
        info = await media.probe(video, 21600)
        output = self.root / 'extracted.wav'
        await media.extract(video, output, info)
        self.assertEqual(media.wav_samples(output, 16000), 32000)
        with wave.open(str(output), 'rb') as audio:
            self.assertFalse(any(audio.readframes(7900)))
            audio.setpos(9000)
            self.assertTrue(any(audio.readframes(1000)))

    async def test_mp3_input_uses_its_audio_timeline(self):
        source = self.root / 'recording.mp3'
        await media.command('ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'sine=frequency=440:sample_rate=16000:duration=1', '-c:a', 'libmp3lame', source)
        info = await media.probe(source, 21600)
        self.assertEqual(info['audio_offset_seconds'], 0)
        self.assertGreaterEqual(info['duration_seconds'], 1)
        output = self.root / 'mp3-extracted.wav'
        await media.extract(source, output, info)
        self.assertEqual(media.wav_samples(output, 16000), info['input_samples'])

    async def test_no_audio_and_overlong_video_are_rejected(self):
        video = self.root / 'silent.mp4'
        await media.command('ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=size=32x32:duration=0.1', video)
        with self.assertRaises(media.MediaError):
            await media.probe(video, 21600)

    def test_sample_boundaries_cover_every_input_sample(self):
        source = self.root / 'source.wav'
        media.write_pcm(source, b'\0' * (241 * 16000 * 2), 16000)
        boundaries = list(media.sections(source))
        self.assertEqual(boundaries[0][0], 0)
        self.assertEqual(boundaries[-1][1], 241 * 16000)
        self.assertTrue(all(a[1] == b[0] for a, b in zip(boundaries, boundaries[1:])))
        self.assertTrue(all(end - start <= 120 * 16000 for start, end in boundaries))

    def test_subtitle_timestamps_and_unknown_languages(self):
        cues = [{'start': 0, 'end': 1.2, 'text': 'नमस्ते'}, {'start': 1.3, 'end': 2, 'text': 'Hello'}]
        srt, vtt = self.root / 'a.srt', self.root / 'a.vtt'
        media.write_subtitles(cues, srt, vtt, 2)
        self.assertIn('00:00:01,200', srt.read_text())
        self.assertTrue(vtt.read_text().startswith('WEBVTT'))
        self.assertFalse(media.valid_cues([{'start': 2, 'end': 1, 'text': 'bad'}], 3))
        self.assertFalse(media.valid_cues([{'start': 0, 'end': float('nan'), 'text': 'bad'}], 3))
        self.assertEqual(languages.whisper_language('zh-Hant'), 'zh')
        self.assertIsNone(languages.whisper_language('rw'))

    def test_space_preflight(self):
        with patch.object(shutil, 'disk_usage', return_value=types.SimpleNamespace(free=10)):
            with self.assertRaises(media.MediaError):
                media.require_space(self.root, 100)


# Avoid initializing a real MongoDB connection, authentication provider, or Whisper model.
import mongomock
from src.database import gemini_jobs_repository as repo
from src.transcription import gemini_worker as worker


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = cfg(self.root)
        self.db = mongomock.MongoClient().db
        self.patches = [patch.object(repo, 'get_db', return_value=self.db), patch.object(repo, 'get_config', return_value=self.config)]
        for p in self.patches:
            p.start()
        repo.enqueue('job_' + 'a' * 32, 'owner@example.test', {'video': 'source.mp4', 'target_language': 'hi'})

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def test_atomic_claim_and_expired_lease_fencing(self):
        first = repo.claim()
        self.assertIsNone(repo.claim())
        self.db.jobs.update_one({'job_id': first['job_id']}, {'$set': {'lease_until': datetime.utcnow() - timedelta(seconds=1)}})
        second = repo.claim()
        self.assertNotEqual(first['lease_token'], second['lease_token'])
        with self.assertRaises(repo.LeaseLost):
            repo.update(first['job_id'], first['lease_token'], stage='wrong')
        repo.heartbeat(second['job_id'], second['lease_token'])
        repo.update(second['job_id'], second['lease_token'], stage='translation')

    def test_checkpoints_are_ordered_and_not_duplicated(self):
        doc = repo.claim()
        section = {'index': 0, 'end_sample': 16000}
        repo.checkpoint(doc['job_id'], doc['lease_token'], section, 32000)
        with self.assertRaises(repo.LeaseLost):
            repo.checkpoint(doc['job_id'], doc['lease_token'], section, 32000)
        saved = self.db.jobs.find_one({'job_id': doc['job_id']})
        self.assertEqual(saved['progress_percentage'], 50)
        self.assertEqual(len(saved['sections']), 1)

    def test_cancel_retry_and_cross_user_actions(self):
        doc = repo.claim()
        self.assertIsNone(repo.request_cancel(doc['job_id'], 'other@example.test'))
        repo.request_cancel(doc['job_id'], 'owner@example.test')
        with self.assertRaises(repo.JobCancelled):
            repo.check(doc['job_id'], doc['lease_token'])
        repo.finish_cancel(doc['job_id'], doc['lease_token'])
        self.assertIsNone(repo.retry(doc['job_id'], 'other@example.test'))
        self.assertEqual(repo.retry(doc['job_id'], 'owner@example.test')['status'], 'pending')

    def test_public_jobs_do_not_expose_paths_or_lease_tokens(self):
        doc = repo.claim()
        doc['source_audio'] = '/private/source.wav'
        doc['artifacts'] = {'wav': '/private/result.wav'}
        public = repo.public_job(doc)
        self.assertNotIn('lease_token', public)
        self.assertNotIn('source_audio', public)
        self.assertEqual(public['artifacts'], {'wav': True})


class LiveProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_drains_output_after_input_end_and_uses_translation_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output = Path(tmp) / 'in.wav', Path(tmp) / 'out.wav'
            tone(source, .2, 16000)
            flushed = asyncio.Event()
            sent = []
            from google.genai import types as gt
            class Session:
                async def send_realtime_input(self, **kwargs):
                    sent.append(kwargs)
                    if kwargs.get('audio_stream_end'):
                        flushed.set()
                async def receive(self):
                    await flushed.wait()
                    yield gt.LiveServerMessage(server_content=gt.LiveServerContent(model_turn=gt.Content(parts=[
                        gt.Part(inline_data=gt.Blob(data=b'\1\0' * 4800, mime_type='audio/pcm;rate=24000'))])))
                    await asyncio.sleep(.01)  # Trailing output must not be lost.
                    yield gt.LiveServerMessage(server_content=gt.LiveServerContent(model_turn=gt.Content(parts=[
                        gt.Part(inline_data=gt.Blob(data=b'\2\0' * 2400, mime_type='audio/pcm;rate=24000'))]), turn_complete=True))
            class Connect:
                async def __aenter__(self): return Session()
                async def __aexit__(self, *args): pass
            connect = Mock(return_value=Connect())
            client = types.SimpleNamespace(aio=types.SimpleNamespace(live=types.SimpleNamespace(connect=connect), aclose=AsyncMock()))
            await translate_section(source, 0, 3200, 'hi', output, 'test', 'gemini-3.5-live-translate-preview',
                                    client_factory=lambda **kwargs: client, paced=False)
            self.assertEqual(media.wav_samples(output), 7200)
            self.assertEqual(len([item for item in sent if 'audio' in item]), 2)
            self.assertTrue(connect.call_args.kwargs['config'].translation_config.echo_target_language)
            self.assertEqual(connect.call_args.kwargs['config'].translation_config.target_language_code, 'hi')
            client.aio.aclose.assert_awaited_once()


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = cfg(self.root)
        Path(self.config.UPLOAD_DIR).mkdir()
        Path(self.config.OUTPUT_DIR).mkdir()
        self.db = mongomock.MongoClient().db
        self.patches = [patch.object(repo, 'get_db', return_value=self.db),
                        patch.object(repo, 'get_config', return_value=self.config),
                        patch.object(worker, 'get_config', return_value=self.config)]
        for p in self.patches:
            p.start()

    async def asyncTearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    async def prepare(self, seconds=1, subtitles=True):
        job_id = 'job_' + 'b' * 32
        video = Path(self.config.UPLOAD_DIR) / (job_id + '_source.mp4')
        await media.command('ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=size=32x32:rate=10:duration={seconds}',
            '-f', 'lavfi', '-i', f'sine=frequency=440:sample_rate=16000:duration={seconds}',
            '-c:v', 'libx264', '-c:a', 'aac', video)
        info = await media.probe(video, 21600)
        repo.enqueue(job_id, 'owner@example.test', {'video': video.name, 'target_language': 'hi',
                     'generate_subtitles': subtitles, 'media_info': info})
        return repo.claim()

    async def test_end_to_end_and_subtitle_retry_reuses_translated_audio(self):
        job = await self.prepare()
        async def translator(source, start, end, target, raw, *args):
            tone(raw, .4)
            return {'input_transcript': 'hello', 'transcripts': [{'start': 0, 'end': .3, 'text': 'नमस्ते'}]}
        translate = AsyncMock(side_effect=translator)
        with patch.object(worker, 'align_subtitles', side_effect=media.MediaError('Subtitle timing unavailable.')):
            await worker.run_claimed(job, translate)
        failed = self.db.jobs.find_one({'job_id': job['job_id']})
        self.assertEqual(failed['status'], 'failed')
        self.assertTrue(Path(failed['artifacts']['wav']).is_file())
        repo.retry(job['job_id'], 'owner@example.test')
        await worker.run_claimed(repo.claim(), translate)
        done = self.db.jobs.find_one({'job_id': job['job_id']})
        self.assertEqual(done['status'], 'done')
        self.assertEqual(translate.await_count, 1)
        self.assertEqual(media.wav_samples(done['artifacts']['wav']), done['media_info']['output_samples'])
        self.assertIn('WEBVTT', Path(done['artifacts']['vtt']).read_text())

    async def test_cancel_stops_work_and_deletion_removes_files(self):
        job = await self.prepare()
        repo.request_cancel(job['job_id'], 'owner@example.test', delete=True)
        translate = AsyncMock()
        await worker.run_claimed(job, translate)
        self.assertIsNone(self.db.jobs.find_one({'job_id': job['job_id']}))
        self.assertFalse((Path(self.config.UPLOAD_DIR) / job['video']).exists())
        translate.assert_not_awaited()

    async def test_low_volume_input_is_not_silently_discarded(self):
        source = self.root / 'quiet.wav'
        tone(source, .1, 16000, amplitude=2)
        self.assertFalse(worker.silent_section(source, 0, 1600))

    async def test_restart_resumes_completed_prefix_without_regenerating_it(self):
        job = await self.prepare(seconds=2, subtitles=False)
        calls = []
        async def initial(source, start, end, target, raw, *args):
            calls.append(start)
            if start == 16000:
                raise asyncio.CancelledError()
            tone(raw, .4)
            return {'input_transcript': 'hello', 'transcripts': []}
        split = [(0, 16000), (16000, 32000)]
        with patch.object(media, 'sections', return_value=iter(split)):
            with self.assertRaises(asyncio.CancelledError):
                await worker.run_claimed(job, initial)
        saved = self.db.jobs.find_one({'job_id': job['job_id']})
        self.assertEqual(len(saved['sections']), 1)
        first_path = saved['sections'][0]['fitted']
        self.db.jobs.update_one({'job_id': job['job_id']}, {'$set': {'lease_until': datetime.utcnow() - timedelta(seconds=1)}})
        async def resume(source, start, end, target, raw, *args):
            calls.append(start)
            tone(raw, .4)
            return {'input_transcript': 'again', 'transcripts': []}
        with patch.object(media, 'sections', return_value=iter(split)):
            await worker.run_claimed(repo.claim(), resume)
        result = self.db.jobs.find_one({'job_id': job['job_id']})
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual(result['sections'][0]['fitted'], first_path)
        self.assertEqual(calls, [0, 16000, 16000])

    async def test_active_cancellation_stops_provider_before_deletion(self):
        job = await self.prepare(subtitles=False)
        started = asyncio.Event()
        stopped = asyncio.Event()
        async def waiting(*args):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
        task = asyncio.create_task(worker.run_claimed(job, waiting))
        await asyncio.wait_for(started.wait(), 3)
        repo.request_cancel(job['job_id'], 'owner@example.test', delete=True)
        await asyncio.wait_for(task, 3)
        self.assertTrue(stopped.is_set())
        self.assertIsNone(self.db.jobs.find_one({'job_id': job['job_id']}))

    async def test_synthetic_three_hour_pipeline_has_exact_duration(self):
        job_id = 'job_' + 'd' * 32
        directory = worker.job_directory(job_id) / 'fixture'
        directory.mkdir(parents=True)
        source = directory / 'source.wav'
        seconds = 3 * 3600
        count = seconds * 16000
        size = count * 2
        # A valid sparse PCM WAV exercises long-file sample math without a huge Python buffer.
        with source.open('wb') as output:
            output.write(b'RIFF' + struct.pack('<I', size + 36) + b'WAVEfmt ' + struct.pack('<IHHIIHH',
                16, 1, 1, 16000, 32000, 2, 16) + b'data' + struct.pack('<I', size))
            output.seek(44 + size - 1)
            output.write(b'\0')
        info = {'duration_seconds': seconds, 'input_samples': count, 'output_samples': seconds * 24000}
        repo.enqueue(job_id, 'owner@example.test', {'video': job_id + '_source.mp4', 'target_language': 'hi',
            'generate_subtitles': False, 'media_info': info, 'source_audio': str(source)})
        translator = AsyncMock()
        await worker.run_claimed(repo.claim(), translator)
        result = self.db.jobs.find_one({'job_id': job_id})
        self.assertEqual(result['status'], 'done', result.get('error'))
        self.assertEqual(media.wav_samples(result['artifacts']['wav']), 3 * 3600 * 24000)
        self.assertEqual(result['processed_duration_seconds'], 10800)
        self.assertTrue(Path(result['artifacts']['mp3']).stat().st_size > 0)
        translator.assert_not_awaited()

    async def test_failed_provider_attempt_does_not_publish_partial_audio(self):
        job = await self.prepare(subtitles=False)
        async def fail(source, start, end, target, raw, *args):
            tone(raw, .2)
            raise ConnectionError('private provider failure')
        # Skip retry delays without changing asyncio's shared sleep implementation.
        with patch.object(worker, 'translate_section', new=AsyncMock()):
            translate = AsyncMock(side_effect=fail)
            original_sleep = asyncio.sleep
            async def fast_sleep(seconds):
                if seconds in (2, 5): return
                await original_sleep(seconds)
            with patch.object(worker.asyncio, 'sleep', side_effect=fast_sleep):
                await worker.run_claimed(job, translate)
        failed = self.db.jobs.find_one({'job_id': job['job_id']})
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['sections'], [])
        self.assertEqual(failed['artifacts'], {})
        self.assertNotIn('private', failed['error'])
        self.assertEqual(translate.await_count, 3)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import httpx
        from fastapi import FastAPI, Request, HTTPException
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = cfg(self.root)
        Path(self.config.UPLOAD_DIR).mkdir()
        Path(self.config.OUTPUT_DIR).mkdir()
        self.db = mongomock.MongoClient().db
        async def user(request: Request):
            email = request.headers.get('x-test-user')
            if not email:
                raise HTTPException(401, 'Sign in')
            return {'email': email}
        auth = types.ModuleType('src.auth.tokens')
        auth.get_current_user = user
        whisper = types.ModuleType('faster_whisper')
        whisper.WhisperModel = Mock()
        riva = types.ModuleType('src.transcription.riva_worker')
        riva.riva_transcribe_job = Mock()
        openai_worker = types.ModuleType('src.transcription.openai_worker')
        openai_worker.openai_transcribe_job = Mock()
        with patch.dict(sys.modules, {'src.auth.tokens': auth, 'faster_whisper': whisper,
                        'src.transcription.riva_worker': riva, 'src.transcription.openai_worker': openai_worker}):
            self.riva = importlib.import_module('src.routes.riva_routes')
            self.openai = importlib.import_module('src.routes.openai_routes')
            self.routes = importlib.import_module('src.routes.transcription_routes')
            self.gemini = importlib.import_module('src.routes.gemini_routes')
        # Repeated tests can reuse the route modules; override their original dependency.
        from commons import limiter
        self.limiter = limiter
        limiter.enabled = False
        self.app = FastAPI()
        self.app.state.limiter = limiter
        self.app.include_router(self.routes.router)
        self.app.include_router(self.gemini.router)
        self.app.include_router(self.riva.router)
        self.app.include_router(self.openai.router)
        self.app.dependency_overrides[self.riva.get_current_user] = user
        self.app.dependency_overrides[self.openai.get_current_user] = user
        self.app.dependency_overrides[self.routes.get_current_user] = user
        self.app.dependency_overrides[self.gemini.get_current_user] = user
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.patches = [patch.object(repo, 'get_db', return_value=self.db),
                       patch.object(repo, 'get_config', return_value=self.config),
                       patch.dict(self.routes.get_job.__globals__, {'get_db': lambda: self.db, 'cfg': self.config}),
                       patch.object(self.gemini, 'get_config', return_value=self.config),
                       patch.object(self.routes, 'cfg', self.config),
                       patch.object(worker, 'get_config', return_value=self.config)]
        for p in self.patches: p.start()
        self.headers = {'x-test-user': 'owner@example.test'}

    async def asyncTearDown(self):
        for p in self.patches: p.stop()
        self.limiter.enabled = True
        await self.client.aclose()
        self.temp.cleanup()

    async def test_upload_is_authenticated_feature_gated_and_validated(self):
        data = {'target_language': 'hi'}
        file = {'file': ('video.mp4', b'not a video', 'video/mp4')}
        self.assertEqual((await self.client.post('/api/gemini/jobs', data=data, files=file)).status_code, 401)
        self.config.GEMINI_TRANSLATION_ENABLED = False
        self.assertFalse((await self.client.get('/api/gemini/capabilities')).json()['enabled'])
        self.assertEqual((await self.client.post('/api/gemini/jobs', data=data, files=file, headers=self.headers)).status_code, 503)
        self.config.GEMINI_TRANSLATION_ENABLED = True
        self.config.GEMINI_API_KEY = ''
        self.assertEqual((await self.client.post('/api/gemini/jobs', data=data, files=file, headers=self.headers)).status_code, 503)
        self.config.GEMINI_API_KEY = 'test-key'
        self.assertEqual((await self.client.post('/api/gemini/jobs', data={'target_language': 'invalid'}, files=file, headers=self.headers)).status_code, 422)
        self.assertEqual((await self.client.post('/api/gemini/jobs', data=data, files=file, headers=self.headers)).status_code, 422)
        self.config.MAX_UPLOAD_SIZE = 3
        self.assertEqual((await self.client.post('/api/gemini/jobs', data=data, files=file, headers=self.headers)).status_code, 413)
        self.assertEqual(list(Path(self.config.UPLOAD_DIR).iterdir()), [])

    async def test_upload_queues_without_api_background_task(self):
        video = self.root / 'valid.mp4'
        await media.command('ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=size=32x32:duration=1',
            '-f', 'lavfi', '-i', 'sine=sample_rate=16000:duration=1', '-c:v', 'libx264', '-c:a', 'aac', video)
        response = await self.client.post('/api/gemini/jobs', headers=self.headers,
            data={'target_language': 'hi', 'generate_subtitles': 'false'},
            files={'file': ('../../original.mp4', video.read_bytes(), 'video/mp4')})
        self.assertEqual(response.status_code, 202, response.text)
        job = self.db.jobs.find_one({'job_id': response.json()['job_id']})
        self.assertEqual(job['status'], 'pending')
        self.assertEqual(job['original_filename'], 'original.mp4')
        self.assertFalse(job['generate_subtitles'])
        self.assertEqual(job['sections'], [])

    async def test_gemini_upload_accepts_mp3_files(self):
        source = self.root / 'recording.mp3'
        await media.command('ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'sine=sample_rate=16000:duration=1', '-c:a', 'libmp3lame', source)
        response = await self.client.post('/api/gemini/jobs', headers=self.headers,
            data={'target_language': 'hi', 'generate_subtitles': 'false'},
            files={'file': ('recording.mp3', source.read_bytes(), 'audio/mpeg')})
        self.assertEqual(response.status_code, 202, response.text)
        job = self.db.jobs.find_one({'job_id': response.json()['job_id']})
        self.assertEqual(job['original_filename'], 'recording.mp3')
        self.assertEqual(job['media_info']['audio_offset_seconds'], 0)

    async def test_existing_engine_upload_routes_keep_their_contracts(self):
        records = []
        def capture(job_id, email, data):
            records.append(dict(data, job_id=job_id, user_email=email))
        for route, module in [('/api/jobs', self.routes), ('/api/riva/jobs', self.riva), ('/api/openai/jobs', self.openai)]:
            with patch.object(module, 'cfg', self.config), patch.object(module, 'create_job', side_effect=capture):
                if module is self.routes:
                    self.config.WHISPER_ALLOWED_MODELS = {'base'}
                    self.config.WHISPER_DEFAULT_MODEL = 'base'
                    worker_patch = patch.object(module, 'transcribe_job', new=Mock())
                else:
                    name = 'riva_transcribe_job' if module is self.riva else 'openai_transcribe_job'
                    worker_patch = patch.object(module, name, new=Mock())
                with worker_patch:
                    response = await self.client.post(route, headers=self.headers,
                        data={'model': 'base', 'language': 'ja', 'translate': 'on'},
                        files={'file': ('legacy.mp4', b'legacy upload fixture', 'video/mp4')})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['status'], 'pending')
        self.assertEqual(len(records), 3)
        self.assertTrue(all(record['user_email'] == 'owner@example.test' and record['translate'] for record in records))

    async def test_artifact_ownership_range_requests_and_legacy_compatibility(self):
        job_id = 'job_' + 'c' * 32
        directory = worker.job_directory(job_id)
        directory.mkdir(parents=True)
        wav = directory / 'master.wav'
        tone(wav, .1)
        srt = directory / 'translated.srt'
        vtt = directory / 'translated.vtt'
        media.write_subtitles([{'start': 0, 'end': .09, 'text': 'hello'}], srt, vtt, .1)
        repo.enqueue(job_id, 'owner@example.test', {'video': job_id + '_source.mp4', 'target_language': 'hi'})
        self.db.jobs.update_one({'job_id': job_id}, {'$set': {'status': 'done', 'artifacts': {'wav': str(wav), 'srt': str(srt), 'vtt': str(vtt)}}})
        wrong = {'x-test-user': 'other@example.test'}
        for path in ['', '/audio', '/subtitles', '/cancel', '/retry']:
            call = self.client.post if path in ['/cancel', '/retry'] else self.client.get
            response = await call('/api/jobs/' + job_id + path, headers=wrong)
            self.assertEqual(response.status_code, 404)
        response = await self.client.get('/api/jobs/' + job_id + '/audio?format=wav', headers={**self.headers, 'Range': 'bytes=0-15'})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(len(response.content), 16)
        self.assertTrue(response.headers['content-range'].startswith('bytes 0-15/'))
        self.assertEqual((await self.client.get('/api/jobs/' + job_id + '/subtitles?format=vtt', headers=self.headers)).status_code, 200)
        self.assertEqual((await self.client.get('/api/jobs/' + job_id + '/audio?format=bad', headers=self.headers)).status_code, 422)
        public = (await self.client.get('/api/jobs/' + job_id, headers=self.headers)).json()
        self.assertEqual(public['artifacts']['wav'], True)
        self.assertNotIn(str(directory), json.dumps(public))
        self.db.jobs.insert_one({'job_id': 'job_abcd', 'user_email': 'owner@example.test', 'status': 'done', 'srt': 'legacy.srt'})
        (Path(self.config.OUTPUT_DIR) / 'legacy.srt').write_text('legacy subtitles')
        old = await self.client.get('/api/jobs/job_abcd/subtitles', headers=self.headers)
        self.assertEqual(old.status_code, 200)
        self.assertEqual(old.text, 'legacy subtitles')
        self.assertEqual((await self.client.post('/api/jobs/job_abcd/retry', headers=self.headers)).status_code, 409)


if __name__ == '__main__':
    unittest.main()
