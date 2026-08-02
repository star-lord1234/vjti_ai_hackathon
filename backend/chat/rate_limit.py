"""Simple in-memory per-session rate limiting for the chat endpoint."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque, Dict

CHAT_MAX_MESSAGES_PER_MINUTE = int(os.getenv("CHAT_MAX_MESSAGES_PER_MINUTE", "20"))
_WINDOW_SECONDS = 60.0

_lock = Lock()
_timestamps: Dict[str, Deque[float]] = defaultdict(deque)


def check_rate_limit(session_id: str) -> bool:
    """Return True if the session is within the allowed message rate."""
    now = time.time()
    cutoff = now - _WINDOW_SECONDS

    with _lock:
        bucket = _timestamps[session_id]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= CHAT_MAX_MESSAGES_PER_MINUTE:
            return False
        bucket.append(now)
        return True


def reset_session(session_id: str) -> None:
    with _lock:
        _timestamps.pop(session_id, None)
