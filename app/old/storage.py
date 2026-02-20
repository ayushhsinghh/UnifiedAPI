import logging
from enum import Enum
from typing import Dict

logger = logging.getLogger(__name__)

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

# This dictionary is kept for backward compatibility only
jobs: Dict[str, dict] = {}
logger.debug("Job storage module initialized")