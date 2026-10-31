"""Correlated translation diagnostics without credentials or transcript content."""
from contextvars import ContextVar
import json
import logging
import os
import re
import traceback

context = ContextVar('gemini_log_context', default={})


class ForwardingFormatter(logging.Formatter):
    """One physical line per record preserves severity and multiline tracebacks."""
    def format(self, record):
        message = record.getMessage()
        if record.exc_info:
            message += '\n' + self.formatException(record.exc_info)
        return json.dumps({'gemini_worker_log': True, 'level': record.levelno,
                           'message': redact(message)})


def redact(value):
    text = str(value)
    for name in ('GEMINI_API_KEY', 'CREDS', 'GOOGLE_API_KEY'):
        secret = os.getenv(name)
        if secret:
            text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?:https?|wss?|mongodb(?:\+srv)?)://[^\s\"\'<>]+', '[REDACTED_URL]', text)
    text = re.sub(r'(?i)(bearer\s+|(?:api[_-]?key|x-goog-api-key|authorization)\s*[=:]\s*)[^\s,;]+',
                  r'\1[REDACTED]', text)
    return text


def event(logger, name, level=logging.INFO, **fields):
    values = dict(context.get(), **fields)
    details = ' '.join(f'{key}={redact(value)}' for key, value in values.items())
    logger.log(level, 'Gemini %s %s', name, details)


def failure(logger, name, exc, **fields):
    # Format first so credentials in exception messages cannot bypass redaction.
    event(logger, name, level=logging.ERROR, error_type=type(exc).__name__,
          error=redact(str(exc)) or '(empty exception message)',
          traceback=redact(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))),
          **fields)
