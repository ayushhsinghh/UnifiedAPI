"""
Data models for the transcription module.
"""

from enum import Enum


class JobStatus(str, Enum):
    """Possible states of a transcription job."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
