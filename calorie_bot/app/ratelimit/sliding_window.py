"""In-memory sliding-window rate limiter keyed by Telegram user id."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Fixed window of timestamps per key; drops timestamps older than ``window_sec``."""

    def __init__(self, *, max_events: int, window_sec: float = 60.0) -> None:
        if max_events < 1:
            raise ValueError("max_events must be at least 1")
        self._max = max_events
        self._window = window_sec
        self._events: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, key: int, *, now: float | None = None) -> bool:
        """Return True if another event is allowed; append timestamp or return False."""
        t = time.monotonic() if now is None else now
        q = self._events[key]
        cutoff = t - self._window
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= self._max:
            return False
        q.append(t)
        return True

    def reset_key(self, key: int) -> None:
        """Drop history for a key (tests)."""
        self._events.pop(key, None)
