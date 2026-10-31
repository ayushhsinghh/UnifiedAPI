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
    def test_api_configuration_has_one_file_and_no_error_or_console_handler(self):
        from logging_config import setup_logging
        with patch('logging.config.dictConfig') as configure, patch('logging.info'):
            setup_logging()
        config = configure.call_args.args[0]
        self.assertEqual(config['root']['handlers'], ['app_log_handler'])
        self.assertEqual(list(config['handlers']), ['app_log_handler'])
        self.assertEqual(Path(config['handlers']['app_log_handler']['filename']).name, 'app.log')
        for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access'):
            self.assertEqual(config['loggers'][name]['handlers'], [])
            self.assertTrue(config['loggers'][name]['propagate'])

    def test_supervised_worker_forwards_without_opening_any_log_file(self):
        from logging_config import setup_logging
        with patch('logging.config.dictConfig') as configure, patch('logging.info'):
            setup_logging(forward_to_parent=True)
        config = configure.call_args.args[0]
        self.assertEqual(list(config['handlers']), ['console'])
        self.assertEqual(config['handlers']['console']['formatter'], 'worker_forward')
        self.assertEqual(config['handlers']['console']['level'], 'DEBUG')

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
