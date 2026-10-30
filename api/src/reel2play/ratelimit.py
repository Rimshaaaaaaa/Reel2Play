"""A small in-memory limit on how often one caller may do something (feature 40).

The caller's address is only hashed with a salt that lives in this process and is never
written anywhere: not to the database, not to the logs. Restarting the API forgets it all.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable
from threading import Lock

_SALT = secrets.token_bytes(16)
MAX_KEYS = 10_000


def caller_key(*parts: str) -> str:
    joined = "\x1f".join(parts).encode("utf-8")
    return hashlib.blake2b(joined, key=_SALT, digest_size=12).hexdigest()


class RateLimiter:
    """At most ``limit`` actions per ``window`` seconds for each key."""

    def __init__(
        self, limit: int, window: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window
        self._clock = clock
        self._seen: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            times = self._seen[key]
            while times and now - times[0] >= self.window:
                times.popleft()
            if len(times) >= self.limit:
                return False
            times.append(now)
            if len(self._seen) > MAX_KEYS:
                self._forget_idle(now)
            return True

    def _forget_idle(self, now: float) -> None:
        """Keep memory bounded: drop callers with nothing inside the window."""
        for key in [k for k, v in self._seen.items() if not v or now - v[-1] >= self.window]:
            del self._seen[key]

    def clear(self) -> None:
        with self._lock:
            self._seen.clear()
