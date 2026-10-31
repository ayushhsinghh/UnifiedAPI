"""Supervise a translation worker within the API's existing service."""
import asyncio
import logging
import os
from pathlib import Path
import signal
import sys

logger = logging.getLogger(__name__)


class GeminiWorkerSupervisor:
    def __init__(self, command=None, retry_seconds=10, stop_seconds=10):
        self.command = command or [sys.executable, '-m', 'src.transcription.gemini_worker']
        self.retry_seconds = retry_seconds
        self.stop_seconds = stop_seconds
        self.process = None

    async def run(self):
        try:
            while True:
                try:
                    spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                        *self.command,
                        cwd=Path(__file__).resolve().parents[2],
                        start_new_session=True,
                    ))
                    try:
                        self.process = await asyncio.shield(spawn)
                    except asyncio.CancelledError:
                        # Reap a child even when shutdown overlaps process creation.
                        self.process = await spawn
                        raise
                    logger.info('Gemini translation worker started: pid=%s', self.process.pid)
                    code = await self.process.wait()
                    await self.stop()
                    logger.warning('Gemini translation worker exited: code=%s; restarting in %ss',
                                   code, self.retry_seconds)
                except OSError:
                    logger.exception('Cannot start Gemini translation worker; retrying')
                await asyncio.sleep(self.retry_seconds)
        finally:
            await self.stop()

    async def stop(self):
        process = self.process
        if process is None:
            return
        logger.info('Stopping Gemini translation worker: pid=%s', process.pid)
        # Include ffmpeg and subtitle subprocesses in shutdown, even if the
        # worker has already exited. Each worker owns its own process group.
        self._signal_group(process.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), timeout=self.stop_seconds)
        except asyncio.TimeoutError:
            logger.warning('Gemini worker shutdown timed out; killing process group: pid=%s', process.pid)
            self._signal_group(process.pid, signal.SIGKILL)
            await process.wait()
        finally:
            self._signal_group(process.pid, signal.SIGKILL)
            self.process = None

    @staticmethod
    def _signal_group(pid, sig):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            pass
