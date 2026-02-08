import logging
import logging.config
from logging.handlers import RotatingFileHandler

def setup_logging():
    """
    Set up centralized logging for the application.
    - Logs to console
    - Rotates `app.log` (max 5MB, keeps 5 backups)
    - Captures errors in `errors.log`
    """
    logging_config = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'default': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'level': 'INFO',
                'formatter': 'default',
            },
            'app_log_handler': {
                'class': 'logging.handlers.RotatingFileHandler',
                'level': 'DEBUG',
                'formatter': 'default',
                'filename': 'app.log',
                'maxBytes': 5 * 1024 * 1024,  # 5 MB
                'backupCount': 5,
                'encoding': 'utf8',
            },
            'error_log_handler': {
                'class': 'logging.FileHandler',
                'level': 'ERROR',
                'formatter': 'default',
                'filename': 'errors.log',
                'encoding': 'utf8',
            },
        },
        'root': {
            'level': 'DEBUG',
            'handlers': ['console', 'app_log_handler', 'error_log_handler'],
        },
    }
    
    logging.config.dictConfig(logging_config)
    logging.info("Logging configured successfully.")

