"""CSRF protection: signed double-submit tokens bound to the session (security.md §5).

    token   = nonce "." mac
    mac     = base64url(HMAC-SHA256(CSRF_SECRET, binding + "|" + nonce))
    binding = "anon" without a valid session, else hex(session token hash)

Nothing is stored: a token is valid if its MAC checks out for the request's
current binding. A token minted for one session is useless for any other, and
an anonymous token stops working once the user signs in (and vice versa).
"""

import base64
import hashlib
import hmac
import secrets
from urllib.parse import urlsplit

from fastapi import Request

from screening_room.config import SettingsDep
from screening_room.core.errors import AppError
from screening_room.modules.identity.dependencies import AuthDep
from screening_room.modules.identity.schemas import AuthenticatedSession

ANONYMOUS_BINDING = "anon"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def binding_for(auth: AuthenticatedSession | None) -> str:
    return auth.token_hash.hex() if auth else ANONYMOUS_BINDING


def mint_csrf_token(secret: str, binding: str) -> str:
    nonce = secrets.token_urlsafe(16)  # 128 bits
    return f"{nonce}.{_mac(secret, binding, nonce)}"


def is_valid_csrf_token(secret: str, binding: str, token: str) -> bool:
    nonce, separator, mac = token.partition(".")
    if not (nonce and separator and mac):
        return False
    # Constant-time comparison, so timing doesn't reveal how much of a guess matched.
    return hmac.compare_digest(mac.encode(), _mac(secret, binding, nonce).encode())


def _mac(secret: str, binding: str, nonce: str) -> str:
    digest = hmac.new(secret.encode(), f"{binding}|{nonce}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def request_origin(request: Request) -> str | None:
    """The Origin header, or the origin of the Referer if Origin is missing."""
    origin = request.headers.get("origin")
    if origin:
        return origin
    referer = urlsplit(request.headers.get("referer", ""))
    if referer.scheme and referer.netloc:
        return f"{referer.scheme}://{referer.netloc}"
    return None


def csrf_protect(request: Request, auth: AuthDep, settings: SettingsDep) -> None:
    """Applied to every route. Checks unsafe requests in the order of security.md §5.3.

    Route-level authentication (401) runs only after this passes.
    """
    if request.method in SAFE_METHODS:
        return

    # 1. Origin allowlist.
    if request_origin(request) not in settings.allowed_origins:
        raise AppError(403, "origin_rejected", "This request's origin is not allowed.")

    # 2-4. Header equals cookie, and the MAC is valid for the current binding
    # (the session was resolved by AuthDep).
    header = request.headers.get(CSRF_HEADER, "")
    cookie = request.cookies.get(settings.csrf_cookie_name, "")
    secret = settings.csrf_secret.get_secret_value()
    if not (
        header
        and hmac.compare_digest(header.encode(), cookie.encode())
        and is_valid_csrf_token(secret, binding_for(auth), header)
    ):
        raise AppError(403, "csrf_failed", "The CSRF check failed. Fetch a new token and retry.")
