"""Small helpers for driving the auth API the way the SPA does."""

from fastapi.testclient import TestClient
from httpx2 import Response

from tests.conftest import TEST_ORIGIN

PASSWORD = "correct horse battery"


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
