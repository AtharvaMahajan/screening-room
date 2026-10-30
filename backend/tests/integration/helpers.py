"""Small helpers for driving the auth API the way the SPA does."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import update
from sqlalchemy.orm import Session

from screening_room.core.security import hash_session_token
from screening_room.modules.identity.models import UserSession
from tests.conftest import TEST_ORIGIN

PASSWORD = "correct horse battery"
SESSION_COOKIE = "sr_session"  # test settings: cookie_prefix_host=False


def expire_session(db_session: Session, client: TestClient) -> None:
    """Make the client's current session expire, as if 30 days had passed."""
    token_hash = hash_session_token(client.cookies[SESSION_COOKIE])
    db_session.execute(
        update(UserSession)
        .where(UserSession.token_hash == token_hash)  # only this test's session
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db_session.commit()  # only releases a savepoint; still undone after the test


def bootstrap_csrf(client: TestClient) -> str:
    """GET /api/auth/session, as the SPA does on startup: returns the CSRF token."""
    response = client.get("/api/auth/session")
    assert response.status_code == 200, response.text
    token: str = response.json()["csrf_token"]
    return token


def post(
    client: TestClient,
    path: str,
    json: object = None,
    *,
    csrf_token: str | None,
    origin: str | None = TEST_ORIGIN,
) -> Response:
    """POST with the headers a same-origin browser request would carry."""
    headers = {}
    if origin is not None:
        headers["Origin"] = origin
    if csrf_token is not None:
        headers["X-CSRF-Token"] = csrf_token
    return client.post(path, json=json, headers=headers)


def register(
    client: TestClient, email: str = "ada@example.com", password: str = PASSWORD
) -> Response:
    token = bootstrap_csrf(client)
    return post(
        client, "/api/auth/register", {"email": email, "password": password}, csrf_token=token
    )


def login(client: TestClient, email: str, password: str = PASSWORD) -> Response:
    token = bootstrap_csrf(client)
    return post(client, "/api/auth/login", {"email": email, "password": password}, csrf_token=token)
