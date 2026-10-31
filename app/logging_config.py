"""
Centralized logging configuration.

The API writes all records to app.log. Supervised workers forward records to
the API over a pipe, so only the API owns and rotates the log file.
"""

import logging
import logging.config

from configs.config import get_config

cfg = get_config()


def setup_logging(forward_to_parent=False) -> None:
    """Configure logging once at application startup."""
    handlers = ["console"] if forward_to_parent else ["app_log_handler"]
    
    logging_handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "worker_forward" if forward_to_parent else "default",
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
    }

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "worker_forward": {
                "()": "src.transcription.gemini_logging.ForwardingFormatter",
            },
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        },
        "handlers": {name: logging_handlers[name] for name in handlers},
        "loggers": {
            name: {"handlers": [], "level": "INFO", "propagate": True}
            for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
        },
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
    if False: # cfg.LOKI_ENDPOINT disabled per user request
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
