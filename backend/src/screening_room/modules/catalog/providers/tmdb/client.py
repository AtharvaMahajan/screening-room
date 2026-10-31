"""HTTP access to the TMDB API: rate limiting, retries and error mapping
(catalog-ingestion.md §10). It returns raw JSON; mapper.py turns that into our types.

The token travels only in the Authorization header. Logs record the request
path and status, never the token or full URLs.
"""

import logging
import random
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx2 as httpx

from screening_room.modules.catalog.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderNotFoundError,
    ProviderUnavailableError,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.themoviedb.org/3"
# connect ~3 s, read ~5 s (catalog-ingestion.md §10).
DEFAULT_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
MAX_RETRY_AFTER_SECONDS = 60.0  # don't let a server stall us indefinitely


class RateLimiter:
    """Spaces requests evenly: at most `rate_per_second`, never in bursts.

    Thread-safe, so a pool of worker threads (M2c) can share one limiter.
    """

    def __init__(
        self,
        rate_per_second: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._interval = 1.0 / rate_per_second
        self._clock = clock
        self._sleep = sleep
        self._next_slot = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until this caller may send a request."""
        with self._lock:
            now = self._clock()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self._interval
        if slot > now:
            self._sleep(slot - now)  # sleep outside the lock

    def pause(self, seconds: float) -> None:
        """Hold back every caller for `seconds` (after a 429 Too Many Requests)."""
        with self._lock:
            self._next_slot = max(self._next_slot, self._clock() + seconds)


class TmdbClient:
    def __init__(
        self,
        token: str,
        *,
        rate_limit_rps: float = 20.0,
        max_attempts: int = 3,  # CLI default; user-facing paths use 2 (one retry)
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        # For tests: a fake transport instead of the network, and control over
        # waiting and randomness.
        transport: httpx.BaseTransport | None = None,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )
        self._limiter = limiter or RateLimiter(rate_limit_rps)
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._jitter = jitter

    def close(self) -> None:
        self._http.close()

    def get_json(self, path: str, params: Mapping[str, str | int] | None = None) -> Any:
        """GET `path`, retrying transient failures. Raises a ProviderError subclass."""
        for attempt in range(1, self._max_attempts + 1):
            self._limiter.acquire()
            try:
                response = self._http.get(path, params=dict(params or {}))
            except httpx.TransportError as exc:  # timeouts, connection errors
                problem = f"{type(exc).__name__}"
                delay = self._backoff(attempt)
            else:
                status = response.status_code
                if status == 200:
                    return response.json()
                if status == 404:
                    raise ProviderNotFoundError(f"TMDB has no {path}")
                if status in (401, 403):
                    # Never retried: the credentials won't fix themselves.
                    raise ProviderAuthError(f"TMDB rejected the credentials ({status})")
                if status == 429:
                    delay = self._retry_after(response) or self._backoff(attempt)
                    self._limiter.pause(delay)  # slow down every thread, not just this one
                elif status >= 500:
                    delay = self._backoff(attempt)
                else:
                    raise ProviderError(f"Unexpected TMDB response {status} for {path}")
                problem = f"HTTP {status}"

            logger.warning(
                "TMDB %s failed (%s), attempt %d of %d",
                path,
                problem,
                attempt,
                self._max_attempts,
                extra={
                    "fields": {
                        "provider": "tmdb",
                        "path": path,
                        "problem": problem,
                        "attempt": attempt,
                        "will_retry": attempt < self._max_attempts,
                    }
                },
            )
            if attempt < self._max_attempts:
                self._sleep(delay)
        raise ProviderUnavailableError(f"TMDB {path} failed after {self._max_attempts} attempts")

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with jitter: about 0.5 s, 1 s, 2 s, ... (max 8 s)."""
        base = min(0.5 * 2.0 ** (attempt - 1), 8.0)
        return base + self._jitter() * base / 2

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        """Seconds from a Retry-After header, if it holds a number."""
        value = response.headers.get("retry-after", "")
        try:
            return min(max(float(value), 0.0), MAX_RETRY_AFTER_SECONDS)
        except ValueError:
            return None
