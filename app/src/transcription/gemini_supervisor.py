"""Supervise a translation worker within the API's existing service."""
import asyncio
import json
import logging
import os
from pathlib import Path
import signal
import sys
from .gemini_logging import redact

logger = logging.getLogger(__name__)


class GeminiWorkerSupervisor:
    def __init__(self, command=None, retry_seconds=10, stop_seconds=10):
        self.command = command or [sys.executable, '-m', 'src.transcription.gemini_worker']
        self.retry_seconds = retry_seconds
        self.stop_seconds = stop_seconds
        self.process = None
        self.output_task = None

    async def forward_output(self, process):
        """Send child diagnostics through the API's single app.log handler."""
        while line := await process.stdout.readline():
            text = line.decode('utf-8', errors='replace').rstrip()
            level = logging.WARNING
            message = text
            try:
                record = json.loads(text)
                if isinstance(record, dict) and record.get('gemini_worker_log') is True:
                    message = str(record['message'])
                    level = int(record['level'])
                    if level not in (10, 20, 30, 40, 50):
                        level = logging.WARNING
            except (ValueError, KeyError, TypeError):
                # Import/startup failures can occur before child logging is configured.
                level = logging.ERROR
            logger.log(level, '[Gemini worker pid=%s] %s', process.pid, redact(message))

    async def run(self):
        try:
            while True:
                try:
                    spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                        *self.command,
                        cwd=Path(__file__).resolve().parents[2],
                        start_new_session=True,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                        limit=1024 * 1024,
                        env=dict(os.environ, SUBFORGE_GEMINI_LOG_FORWARDING='1', PYTHONUNBUFFERED='1'),
                    ))
                    try:
                        self.process = await asyncio.shield(spawn)
                    except asyncio.CancelledError:
                        # Reap a child even when shutdown overlaps process creation.
                        self.process = await spawn
                        self.output_task = asyncio.create_task(self.forward_output(self.process))
                        raise
                    self.output_task = asyncio.create_task(self.forward_output(self.process))
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
            if self.output_task is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(self.output_task), timeout=3)
                except asyncio.TimeoutError:
                    self.output_task.cancel()
                    await asyncio.gather(self.output_task, return_exceptions=True)
                    logger.error('Timed out draining Gemini worker logs: pid=%s', process.pid)
                except Exception:
                    logger.exception('Failed to forward Gemini worker logs: pid=%s', process.pid)
                finally:
                    self.output_task = None

    @staticmethod
    def _signal_group(pid, sig):
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            pass
