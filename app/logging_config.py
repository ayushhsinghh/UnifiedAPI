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
    handlers = ["console", "app_log_handler", "error_log_handler"]
    
    logging_handlers = {
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
    }

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": logging_handlers,
        "root": {
            "level": "DEBUG",
            "handlers": handlers,
        },
    }

    logging.config.dictConfig(logging_config)
    
    # Add Loki handler manually if configured
    # We do this AFTER dictConfig because LokiQueueHandler requires 
    # an actual multiprocessing/threading Queue object which dictConfig 
    # struggles to instantiate correctly.
    if cfg.LOKI_ENDPOINT:
        import logging_loki
        import queue
        
        auth = None
        if cfg.LOKI_USERNAME and cfg.LOKI_PASSWORD:
            auth = (cfg.LOKI_USERNAME, cfg.LOKI_PASSWORD)
            
        loki_handler = logging_loki.LokiQueueHandler(
            queue=queue.Queue(maxsize=1000),
            url=cfg.LOKI_ENDPOINT,
            tags=cfg.LOKI_TAGS,
            auth=auth,
            version="1",
        )
        loki_handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(loki_handler)
        
    logging.info("Logging configured successfully.")
