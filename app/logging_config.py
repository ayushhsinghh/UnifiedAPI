"""
Centralized logging configuration.

Sets up:
- Console handler (INFO level)
- Rotating file handler for app.log (DEBUG level)
- Separate file handler for errors.log (ERROR level)
"""

import logging
import logging.config

from configs.config import get_config

cfg = get_config()


def setup_logging() -> None:
    """Configure logging once at application startup."""
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "default",
            },
            "app_log_handler": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "default",
                "filename": cfg.LOG_FILE_APP,
                "maxBytes": cfg.LOG_MAX_BYTES,
                "backupCount": cfg.LOG_BACKUP_COUNT,
                "encoding": "utf8",
            },
            "error_log_handler": {
                "class": "logging.FileHandler",
                "level": "ERROR",
                "formatter": "default",
                "filename": cfg.LOG_FILE_ERRORS,
                "encoding": "utf8",
            },
        },
        "root": {
            "level": "DEBUG",
            "handlers": ["console", "app_log_handler", "error_log_handler"],
        },
    }

    logging.config.dictConfig(logging_config)
    logging.info("Logging configured successfully.")
