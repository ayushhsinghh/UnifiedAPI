"""Exercise real child-process startup, recovery, and shutdown without Gemini."""
import asyncio
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


if __name__ == '__main__':
    unittest.main()
