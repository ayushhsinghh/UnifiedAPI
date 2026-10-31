"""Diagnostics retain useful errors and context while removing credentials."""
import asyncio
import logging
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from src.transcription.gemini_logging import context, event, failure
from src.transcription import gemini_media as media


class LoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_contains_traceback_and_redacts_credentials(self):
        token = context.set({'job': 'job_test', 'stage': 'translation', 'section': 2, 'attempt': 3})
        logger = logging.getLogger('gemini_logging_test')
        try:
            with patch.dict('os.environ', {'GEMINI_API_KEY': 'secret-test-value', 'CREDS': 'db-secret-value'}):
                with self.assertLogs(logger, level='ERROR') as logs:
                    try:
                        raise ConnectionError('model unavailable secret-test-value db-secret-value '
                                              'wss://example.test/live?key=abc Authorization=Bearer-secret')
                    except ConnectionError as exc:
                        failure(logger, 'translation_attempt_failed', exc)
            output = '\n'.join(logs.output)
            for value in ('secret-test-value', 'db-secret-value', 'key=abc', 'Bearer-secret'):
                self.assertNotIn(value, output)
            for value in ('job=job_test', 'stage=translation', 'section=2', 'attempt=3',
                          'ConnectionError', 'model unavailable', 'Traceback (most recent call last)'):
                self.assertIn(value, output)
        finally:
            context.reset(token)

    async def test_thread_work_keeps_job_context(self):
        token = context.set({'job': 'job_thread'})
        try:
            with self.assertLogs('gemini_logging_test', level='INFO') as logs:
                await asyncio.to_thread(event, logging.getLogger('gemini_logging_test'), 'subtitle_started')
            self.assertIn('job=job_thread', logs.output[0])
        finally:
            context.reset(token)

    async def test_media_failure_logs_stderr_but_keeps_public_error_short(self):
        with self.assertLogs('src.transcription.gemini_media', level='ERROR') as logs:
            with self.assertRaisesRegex(media.MediaError, r'failed \(exit 2\)') as error:
                await media.command(sys.executable, '-c',
                                    'import sys; sys.stderr.write("decoder unavailable"); sys.exit(2)')
        self.assertIn('decoder unavailable', '\n'.join(logs.output))
        self.assertIn('exit_code=2', '\n'.join(logs.output))
        self.assertNotIn('decoder unavailable', str(error.exception))


if __name__ == '__main__':
    unittest.main()
