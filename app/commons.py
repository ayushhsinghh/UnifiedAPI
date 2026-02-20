"""
Shared utility functions and singletons used across multiple modules.
"""

import random
import string

from slowapi import Limiter
from slowapi.util import get_remote_address

# ── Shared rate-limiter instance ─────────────────────────────────────────
# Created here (not in main.py) so that route modules can import it
# without a circular dependency.
limiter = Limiter(key_func=get_remote_address)


def generate_job_id() -> str:
    """Generate a short, memorable job ID (e.g., 'job_a1b2')."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(random.choices(chars, k=4))
    return f"job_{random_part}"
