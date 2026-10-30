"""Register, sign in, sign out and session lookup against real PostgreSQL (ADR-0007)."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from screening_room.core.security import hash_session_token
from screening_room.modules.identity.models import User, UserSession
from tests.conftest import TEST_ORIGIN
from tests.integration.helpers import (
    PASSWORD,
    SESSION_COOKIE,
    bootstrap_csrf,
    expire_session,
    login,
    post,
    register,
)

CSRF_COOKIE = "sr_csrf"


def set_cookie_header(response_headers: list[str], name: str) -> str:
    matches = [header for header in response_headers if header.startswith(f"{name}=")]
    assert len(matches) == 1, f"expected one Set-Cookie for {name}: {response_headers}"
    return matches[0].lower()


# --- Session bootstrap -------------------------------------------------------------


def test_anonymous_visitor_gets_a_csrf_token_and_no_user(client: TestClient) -> None:
    response = client.get("/api/auth/session")

    assert response.status_code == 200
    body = response.json()
    assert body["user"] is None
    assert body["csrf_token"] == client.cookies[CSRF_COOKIE]  # double-submit copy


def test_a_still_valid_csrf_cookie_is_reused(client: TestClient) -> None:
    first = bootstrap_csrf(client)

    response = client.get("/api/auth/session")

    assert response.json()["csrf_token"] == first
    assert "set-cookie" not in response.headers  # nothing to change


# --- Registration ----------------------------------------------------------------------


def test_register_signs_the_user_in(client: TestClient) -> None:
    anonymous_token = bootstrap_csrf(client)

    response = post(
        client,
        "/api/auth/register",
        {"email": "  Ada@Example.COM ", "password": PASSWORD, "display_name": "Ada"},
        csrf_token=anonymous_token,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"] == {"email": "ada@example.com", "display_name": "Ada"}
    # The CSRF token is rotated to one bound to the new session.
    assert body["csrf_token"] != anonymous_token
    assert body["csrf_token"] == client.cookies[CSRF_COOKIE]
    # And the session now resolves.
    assert client.get("/api/auth/session").json()["user"]["email"] == "ada@example.com"


def test_session_cookie_is_httponly_and_samesite_lax(client: TestClient) -> None:
    response = register(client)

    cookies = response.headers.get_list("set-cookie")
    session_cookie = set_cookie_header(cookies, SESSION_COOKIE)
    csrf_cookie = set_cookie_header(cookies, CSRF_COOKIE)
    assert "httponly" in session_cookie and "samesite=lax" in session_cookie
    assert "max-age=" in session_cookie  # 30-day absolute lifetime
    # The CSRF copy must be readable by the SPA, so it is NOT HttpOnly.
    assert "httponly" not in csrf_cookie


def test_only_a_hash_of_the_session_token_is_stored(
    client: TestClient, db_session: Session
) -> None:
    register(client, email="hash-check@example.com")
    token = client.cookies[SESSION_COOKIE]

    # Only this test's user: the database may already hold other data.
    stored = db_session.scalars(
        select(UserSession.token_hash)
        .join(User, User.id == UserSession.user_id)
        .where(User.email == "hash-check@example.com")
    ).all()

    # Also proves requests write through the test's db_session (the M1b gap).
    assert stored == [hash_session_token(token)]
    assert token.encode() not in stored


def test_password_is_stored_as_an_argon2id_hash(client: TestClient, db_session: Session) -> None:
    register(client, email="argon-check@example.com")

    user = db_session.scalars(select(User).where(User.email == "argon-check@example.com")).one()

    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


def test_registering_an_existing_email_is_a_conflict(client: TestClient) -> None:
    register(client, email="ada@example.com")
    client.cookies.clear()  # a different visitor

    response = register(client, email="ADA@example.com")  # same after normalization

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_unavailable"


def test_short_password_is_rejected_with_field_details(client: TestClient) -> None:
    response = register(client, password="too-short")

    assert response.status_code == 422
    assert [d["field"] for d in response.json()["error"]["details"]] == ["body.password"]


# --- Login -------------------------------------------------------------------------------


def test_login_with_correct_password(client: TestClient) -> None:
    register(client)
    client.cookies.clear()

    response = login(client, "ada@example.com")

    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == "ada@example.com"


def test_wrong_password_and_unknown_email_get_the_same_answer(client: TestClient) -> None:
    register(client)
    client.cookies.clear()

    wrong_password = login(client, "ada@example.com", password="not the password")
    unknown_email = login(client, "nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert (
        wrong_password.json()
        == unknown_email.json()
        == {"error": {"code": "invalid_credentials", "message": "Invalid email or password."}}
    )


def test_login_issues_a_new_session_and_revokes_the_presented_one(
    client: TestClient, db_session: Session
) -> None:
    register(client)
    old_token = client.cookies[SESSION_COOKIE]

    login(client, "ada@example.com")  # while still carrying the old session cookie

    new_token = client.cookies[SESSION_COOKIE]
    assert new_token != old_token
    old = db_session.scalars(
        select(UserSession).where(UserSession.token_hash == hash_session_token(old_token))
    ).one()
    assert old.revoked_at is not None  # session fixation hygiene (security.md §3)


# --- Logout --------------------------------------------------------------------------------


def test_logout_revokes_the_session_and_returns_an_anonymous_token(
    client: TestClient, db_session: Session
) -> None:
    signed_in_token = register(client).json()["csrf_token"]
    session_token = client.cookies[SESSION_COOKIE]

    response = post(client, "/api/auth/logout", csrf_token=signed_in_token)

    assert response.status_code == 200, response.text
    assert response.json()["user"] is None
    assert SESSION_COOKIE not in client.cookies  # cookie cleared
    revoked = db_session.scalars(
        select(UserSession.revoked_at).where(
            UserSession.token_hash == hash_session_token(session_token)
        )
    ).one()
    assert revoked is not None
    # The returned anonymous token works straight away for signing back in.
    again = post(
        client,
        "/api/auth/login",
        {"email": "ada@example.com", "password": PASSWORD},
        csrf_token=response.json()["csrf_token"],
    )
    assert again.status_code == 200, again.text


def test_a_revoked_session_cookie_no_longer_signs_anyone_in(client: TestClient) -> None:
    signed_in_token = register(client).json()["csrf_token"]
    session_token = client.cookies[SESSION_COOKIE]
    post(client, "/api/auth/logout", csrf_token=signed_in_token)

    client.cookies.set(SESSION_COOKIE, session_token)  # replay the old cookie

    assert client.get("/api/auth/session").json()["user"] is None


def test_an_expired_session_is_treated_as_signed_out(
    client: TestClient, db_session: Session
) -> None:
    register(client)
    signed_in_csrf = client.cookies[CSRF_COOKIE]
    expire_session(db_session, client)

    body = client.get("/api/auth/session").json()

    assert body["user"] is None
    # The session-bound CSRF cookie no longer matches, so an anonymous one is issued.
    assert body["csrf_token"] != signed_in_csrf
    assert body["csrf_token"] == client.cookies[CSRF_COOKIE]


# --- JSON only (security.md §7) --------------------------------------------------------


@pytest.mark.parametrize("content_type", ["application/x-www-form-urlencoded", "text/plain", None])
def test_non_json_bodies_are_never_processed(client: TestClient, content_type: str | None) -> None:
    # Content types a cross-site form or a no-preflight fetch can send. Even with a
    # valid CSRF token, the body must not be read as JSON.
    register(client)
    client.cookies.clear()
    token = bootstrap_csrf(client)
    headers = {"Origin": TEST_ORIGIN, "X-CSRF-Token": token}
    if content_type:
        headers["Content-Type"] = content_type

    response = client.post(
        "/api/auth/login",
        content=json.dumps({"email": "ada@example.com", "password": PASSWORD}),
        headers=headers,
    )

    assert response.status_code == 422, response.text
    assert SESSION_COOKIE not in client.cookies
