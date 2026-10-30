"""CSRF token mechanics and Origin parsing (security.md §5.1, §5.3)."""

import pytest
from starlette.requests import Request

from screening_room.modules.identity.csrf import (
    ANONYMOUS_BINDING,
    is_valid_csrf_token,
    mint_csrf_token,
    request_origin,
)

SECRET = "unit-test-secret-that-is-at-least-32-chars"
SESSION_BINDING = "ab" * 32  # hex of a 32-byte session token hash


def test_minted_token_is_valid_for_its_binding() -> None:
    token = mint_csrf_token(SECRET, ANONYMOUS_BINDING)

    assert is_valid_csrf_token(SECRET, ANONYMOUS_BINDING, token)


def test_token_is_invalid_for_another_binding() -> None:
    # An anonymous token can't be used once signed in, and vice versa.
    anonymous = mint_csrf_token(SECRET, ANONYMOUS_BINDING)
    signed_in = mint_csrf_token(SECRET, SESSION_BINDING)

    assert not is_valid_csrf_token(SECRET, SESSION_BINDING, anonymous)
    assert not is_valid_csrf_token(SECRET, ANONYMOUS_BINDING, signed_in)


def test_token_is_invalid_under_another_secret() -> None:
    # Rotating CSRF_SECRET invalidates every outstanding token (security.md §5.7).
    token = mint_csrf_token(SECRET, ANONYMOUS_BINDING)

    assert not is_valid_csrf_token(
        "a-different-secret-also-32-characters", ANONYMOUS_BINDING, token
    )


def test_tampered_token_is_invalid() -> None:
    nonce, mac = mint_csrf_token(SECRET, ANONYMOUS_BINDING).split(".")
    other_nonce, _ = mint_csrf_token(SECRET, ANONYMOUS_BINDING).split(".")

    assert not is_valid_csrf_token(SECRET, ANONYMOUS_BINDING, f"{other_nonce}.{mac}")
    assert not is_valid_csrf_token(SECRET, ANONYMOUS_BINDING, f"{nonce}.{mac[:-1]}x")


@pytest.mark.parametrize("token", ["", "no-dot", ".", "nonce.", ".mac", "é.ü", "a.b.c"])
def test_malformed_tokens_are_invalid_not_errors(token: str) -> None:
    assert not is_valid_csrf_token(SECRET, ANONYMOUS_BINDING, token)


def test_tokens_are_unique() -> None:
    assert len({mint_csrf_token(SECRET, ANONYMOUS_BINDING) for _ in range(50)}) == 50


def _request(headers: dict[str, str]) -> Request:
    raw = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "method": "POST", "headers": raw})


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"Origin": "http://localhost:5173"}, "http://localhost:5173"),
        # Origin wins over Referer when both are present.
        ({"Origin": "https://a.test", "Referer": "https://b.test/x"}, "https://a.test"),
        # Referer fallback: only scheme://host:port, never the path.
        ({"Referer": "http://localhost:5173/settings?tab=1"}, "http://localhost:5173"),
        ({"Referer": "not a url"}, None),
        ({}, None),
    ],
)
def test_request_origin(headers: dict[str, str], expected: str | None) -> None:
    assert request_origin(_request(headers)) == expected
