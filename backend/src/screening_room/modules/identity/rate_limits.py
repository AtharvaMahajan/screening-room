"""Login and registration rate limits (security.md §8): slow down password guessing
and mass sign-ups. Fixed windows per IP and per email address, in memory.

- Login, per IP: every attempt counts.
- Login, per email: only FAILED attempts count. Counting successes too would let
  anyone lock a real user out just by trying their address.
- Registration, per IP: every attempt counts.

Over the limit: 429 `rate_limited`, with Retry-After.
"""

import logging
from typing import Annotated

from fastapi import Depends, Request

from screening_room.config import Settings
from screening_room.core.errors import AppError
from screening_room.core.rate_limit import FixedWindowLimiter
from screening_room.modules.identity.service import normalize_email

logger = logging.getLogger(__name__)


class AuthRateLimits:
    def __init__(self, settings: Settings) -> None:
        login_window = settings.login_window_minutes * 60
        self._login_ip = FixedWindowLimiter(settings.login_attempts_per_ip, login_window)
        self._login_email = FixedWindowLimiter(settings.login_failures_per_email, login_window)
        self._register_ip = FixedWindowLimiter(
            settings.registrations_per_ip, settings.registration_window_minutes * 60
        )

    def before_login(self, ip: str, email: str) -> None:
        _refuse_if_limited("login_per_ip", self._login_ip.retry_after(ip))
        _refuse_if_limited(
            "login_failures_per_email", self._login_email.retry_after(normalize_email(email))
        )
        self._login_ip.hit(ip)

    def login_failed(self, email: str) -> None:
        self._login_email.hit(normalize_email(email))

    def before_registration(self, ip: str) -> None:
        _refuse_if_limited("registration_per_ip", self._register_ip.retry_after(ip))
        self._register_ip.hit(ip)


def _refuse_if_limited(policy: str, retry_after: int | None) -> None:
    if retry_after is not None:
        # The policy only: never the email address or IP (security.md §9).
        logger.warning("rate limited", extra={"fields": {"policy": policy}})
        raise AppError(
            429,
            "rate_limited",
            "Too many attempts. Please wait a few minutes and try again.",
            headers={"Retry-After": str(retry_after)},
        )


def client_ip(request: Request) -> str:
    """The caller's IP. Behind a proxy in production, uvicorn must be started with
    --proxy-headers (and trusted --forwarded-allow-ips) so this is the real client."""
    return request.client.host if request.client else "unknown"


def get_auth_rate_limits(request: Request) -> AuthRateLimits:
    limits: AuthRateLimits = request.app.state.auth_rate_limits
    return limits


AuthRateLimitsDep = Annotated[AuthRateLimits, Depends(get_auth_rate_limits)]
