"""Exercise real child-process startup, recovery, and shutdown without Gemini."""
import asyncio
import json
import logging
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from src.transcription.gemini_supervisor import GeminiWorkerSupervisor


class SupervisorTests(unittest.IsolatedAsyncioTestCase):
    async def wait_until(self, condition):
        async def poll():
            while not condition():
                await asyncio.sleep(0.01)
        await asyncio.wait_for(poll(), timeout=5)

    async def test_starts_and_stops_worker(self):
        supervisor = GeminiWorkerSupervisor(
            [sys.executable, '-c', 'import time; time.sleep(60)'])
        task = asyncio.create_task(supervisor.run())
        try:
            await self.wait_until(lambda: supervisor.process is not None)
            process = supervisor.process
            self.assertIsNone(process.returncode)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertIsNotNone(process.returncode)
        self.assertIsNone(supervisor.process)

    async def test_restarts_exited_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'started'
            code = (
                'from pathlib import Path; import time; '
                f'p=Path({str(marker)!r}); '
                'exists=p.exists(); p.write_text("started"); '
                'time.sleep(60 if exists else 0)'
            )
            supervisor = GeminiWorkerSupervisor(
                [sys.executable, '-c', code], retry_seconds=0.02)
            task = asyncio.create_task(supervisor.run())
            try:
                await self.wait_until(lambda: supervisor.process is not None)
                first_pid = supervisor.process.pid
                await self.wait_until(lambda: supervisor.process is not None
                                      and supervisor.process.pid != first_pid)
                self.assertTrue(marker.exists())
                process = supervisor.process
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self.assertIsNotNone(process.returncode)

    async def test_retries_spawn_failure(self):
        supervisor = GeminiWorkerSupervisor(['/nonexistent/subforge-worker'], retry_seconds=0.01)
        task = asyncio.create_task(supervisor.run())
        try:
            with self.assertLogs('src.transcription.gemini_supervisor', level='ERROR') as logs:
                await self.wait_until(lambda: len(logs.output) >= 2)
            self.assertFalse(task.done())
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_kills_worker_that_ignores_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'ready'
            code = (
                'import signal, time; from pathlib import Path; '
                'signal.signal(signal.SIGTERM, signal.SIG_IGN); '
                f'Path({str(marker)!r}).touch(); time.sleep(60)'
            )
            supervisor = GeminiWorkerSupervisor(
                [sys.executable, '-c', code], stop_seconds=0.05)
            task = asyncio.create_task(supervisor.run())
            try:
                await self.wait_until(marker.exists)
                process = supervisor.process
            finally:
                task.cancel()
                await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=2)
            self.assertEqual(process.returncode, -9)

    async def test_worker_messages_reach_app_log_with_original_severity(self):
        with tempfile.TemporaryDirectory() as directory:
            app_log = Path(directory) / 'app.log'
            logger = logging.getLogger('src.transcription.gemini_supervisor')
            app_handler = logging.FileHandler(app_log)
            app_handler.setLevel(logging.INFO)
            app_handler.setFormatter(logging.Formatter('%(levelname)s:%(message)s'))
            old_level = logger.level
            logger.setLevel(logging.INFO)
            logger.addHandler(app_handler)
            info = json.dumps({'gemini_worker_log': True, 'level': 20,
                               'message': 'Gemini live_connected job=job_forwarding'})
            error = json.dumps({'gemini_worker_log': True, 'level': 40,
                                'message': 'Gemini job_failed job=job_forwarding\nConnectionError: unavailable'})
            code = f'import sys, time; print({info!r}, flush=True); print({error!r}, file=sys.stderr, flush=True); time.sleep(60)'
            supervisor = GeminiWorkerSupervisor([sys.executable, '-c', code])
            task = asyncio.create_task(supervisor.run())
            try:
                await self.wait_until(lambda: 'ConnectionError: unavailable' in app_log.read_text())
                self.assertIn('Gemini live_connected job=job_forwarding', app_log.read_text())
                self.assertIn('Gemini job_failed job=job_forwarding', app_log.read_text())
                self.assertIn('INFO:[Gemini worker', app_log.read_text())
                self.assertIn('ERROR:[Gemini worker', app_log.read_text())
                self.assertNotIn('gemini_worker_log', app_log.read_text())
                self.assertEqual([p.name for p in Path(directory).iterdir()], ['app.log'])
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                logger.removeHandler(app_handler)
                app_handler.close()
                logger.setLevel(old_level)

    async def test_startup_traceback_is_forwarded_to_parent(self):
        supervisor = GeminiWorkerSupervisor(
            [sys.executable, '-c', 'raise RuntimeError("worker import failed")'], retry_seconds=60)
        task = asyncio.create_task(supervisor.run())
        try:
            with self.assertLogs('src.transcription.gemini_supervisor', level='ERROR') as logs:
                await self.wait_until(lambda: any('RuntimeError: worker import failed' in line for line in logs.output))
            self.assertIn('Traceback', '\n'.join(logs.output))
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


if __name__ == '__main__':
    unittest.main()
