"""In-process fixed-window rate limiting (security.md §8).

One API instance, so counts live in memory. If the app ever runs as several
instances, this moves to PostgreSQL (ADR-0002) so they share the counts.

Fixed windows are simple and predictable: a key may be hit `limit` times per
window, and the window restarts after `window_seconds`. Bursts at a window
edge can reach twice the limit, which is fine for slowing password guessing.
"""

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class _Window:
    started: float
    hits: int


class FixedWindowLimiter:
    """Thread-safe: sync handlers run in a thread pool (ADR-0006)."""

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._max_keys = max_keys  # bounds memory if many distinct keys show up
        self._windows: dict[str, _Window] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int | None:
        """Seconds until `key` may try again, or None if it's under the limit."""
        with self._lock:
            window = self._current(key)
            if window is None or window.hits < self._limit:
                return None
            return max(1, math.ceil(window.started + self._window - self._clock()))

    def hit(self, key: str) -> None:
        """Count one attempt for `key`."""
        with self._lock:
            window = self._current(key)
            if window is None:
                if len(self._windows) >= self._max_keys:
                    self._prune()
                window = self._windows[key] = _Window(started=self._clock(), hits=0)
            window.hits += 1

    def _current(self, key: str) -> _Window | None:
        window = self._windows.get(key)
        if window is not None and self._clock() - window.started >= self._window:
            del self._windows[key]  # expired: a fresh window starts on the next hit
            return None
        return window

    def _prune(self) -> None:
        now = self._clock()
        for key in [k for k, w in self._windows.items() if now - w.started >= self._window]:
            del self._windows[key]
        if len(self._windows) >= self._max_keys:  # all still active: drop the oldest
            oldest = min(self._windows, key=lambda k: self._windows[k].started)
            del self._windows[oldest]
