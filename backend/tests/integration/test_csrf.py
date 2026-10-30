"""CSRF and Origin checks on unsafe requests (security.md §5.3).

The roadmap's M1 matrix: anonymous, authenticated, expired-session and
cross-origin cases. Checks run in this order: Origin -> CSRF -> route auth (401).
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy.orm import Session

from screening_room.modules.identity.dependencies import CurrentUserDep
from tests.integration.helpers import PASSWORD, bootstrap_csrf, expire_session, post, register

PROTECTED = "/api/test/protected"
LOGIN = "/api/auth/login"


@pytest.fixture
def client(client: TestClient) -> Iterator[TestClient]:
    """The standard client, plus a protected POST route like future /api/me/... ones."""

    def protected(user: CurrentUserDep) -> dict[str, str]:
        return {"email": user.email}

    app = client.app
    assert isinstance(app, FastAPI)
    app.add_api_route(PROTECTED, protected, methods=["POST"])
    yield client


def signed_in(client: TestClient) -> str:
    """Register and return the session-bound CSRF token."""
    response = register(client)
    assert response.status_code == 201, response.text
    token: str = response.json()["csrf_token"]
    return token


def error_code(response: Response) -> str:
    code: str = response.json()["error"]["code"]
    return code


# --- Origin ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "origin", [None, "https://evil.example", "http://testserver.evil.example", "null"]
)
def test_unsafe_request_from_a_disallowed_origin_is_rejected(
    client: TestClient, origin: str | None
) -> None:
    token = bootstrap_csrf(client)  # even with a perfectly valid token

    response = post(
        client, LOGIN, {"email": "a@b.co", "password": PASSWORD}, csrf_token=token, origin=origin
    )

    assert response.status_code == 403
    assert error_code(response) == "origin_rejected"


def test_referer_is_used_when_origin_is_missing(client: TestClient) -> None:
    token = bootstrap_csrf(client)

    response = client.post(
        PROTECTED,
        headers={"Referer": "http://testserver/some/page", "X-CSRF-Token": token},
    )

    # Origin and CSRF passed, so the route's own auth check answered.
    assert error_code(response) == "unauthenticated"


# --- CSRF token -------------------------------------------------------------------------


def test_missing_csrf_header_is_rejected(client: TestClient) -> None:
    bootstrap_csrf(client)  # the cookie is there, the header isn't

    response = post(client, PROTECTED, csrf_token=None)

    assert response.status_code == 403
    assert error_code(response) == "csrf_failed"


def test_header_that_differs_from_the_cookie_is_rejected(client: TestClient) -> None:
    bootstrap_csrf(client)
    other_valid_token = TestClient(client.app).get("/api/auth/session").json()["csrf_token"]

    response = post(client, PROTECTED, csrf_token=other_valid_token)

    assert error_code(response) == "csrf_failed"


def test_forged_token_in_both_header_and_cookie_is_rejected(client: TestClient) -> None:
    # Planting the same value in cookie and header isn't enough: it must be signed.
    forged = "attacker-nonce.attacker-mac"
    client.cookies.set("sr_csrf", forged)

    response = post(client, PROTECTED, csrf_token=forged)

    assert error_code(response) == "csrf_failed"


def test_anonymous_token_stops_working_after_sign_in(client: TestClient) -> None:
    anonymous_token = bootstrap_csrf(client)
    signed_in(client)
    client.cookies.set("sr_csrf", anonymous_token)  # pretend the cookie wasn't rotated

    response = post(client, PROTECTED, csrf_token=anonymous_token)

    assert error_code(response) == "csrf_failed"


def test_token_from_another_users_session_is_rejected(client: TestClient) -> None:
    signed_in(client)
    other = TestClient(client.app)
    other_token = register(other, email="mallory@example.com").json()["csrf_token"]
    client.cookies.set("sr_csrf", other_token)

    response = post(client, PROTECTED, csrf_token=other_token)

    assert error_code(response) == "csrf_failed"


def test_expired_session_makes_its_token_fail_then_rebootstrap_works(
    client: TestClient, db_session: Session
) -> None:
    token = signed_in(client)
    expire_session(db_session, client)

    rejected = post(client, PROTECTED, csrf_token=token)
    fresh_token = bootstrap_csrf(client)  # what the SPA does after csrf_failed
    retried = post(client, PROTECTED, csrf_token=fresh_token)

    assert error_code(rejected) == "csrf_failed"
    assert error_code(retried) == "unauthenticated"  # now it's just signed out


# --- Order of checks and the happy paths -------------------------------------------------


def test_csrf_runs_before_authentication(client: TestClient) -> None:
    # No session and no token: the CSRF failure is reported, not the 401.
    response = post(client, PROTECTED, csrf_token=None)

    assert error_code(response) == "csrf_failed"


def test_valid_anonymous_token_without_session_gets_401(client: TestClient) -> None:
    response = post(client, PROTECTED, csrf_token=bootstrap_csrf(client))

    assert response.status_code == 401
    assert error_code(response) == "unauthenticated"


def test_signed_in_request_with_valid_token_succeeds(client: TestClient) -> None:
    response = post(client, PROTECTED, csrf_token=signed_in(client))

    assert response.status_code == 200, response.text
    assert response.json() == {"email": "ada@example.com"}


def test_safe_methods_need_no_origin_or_token(client: TestClient) -> None:
    assert client.get("/api/auth/session").status_code == 200
    assert client.get("/api/health").status_code == 200
