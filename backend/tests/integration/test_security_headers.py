"""Security headers on every response (security.md §7)."""

import pytest
from fastapi.testclient import TestClient

from screening_room.config import Settings
from screening_room.core.headers import TMDB_IMAGES
from screening_room.main import create_app

EXPECTED = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/health"),  # a normal response
        ("GET", "/api/no-such-route"),  # an error
        ("POST", "/api/auth/login"),  # rejected before the handler (CSRF)
        ("GET", "/api/me/favorites"),  # rejected by authentication
    ],
)
def test_every_response_carries_the_headers(client: TestClient, method: str, path: str) -> None:
    response = client.request(method, path)

    assert {name: response.headers.get(name) for name in EXPECTED} == EXPECTED
    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert f"img-src 'self' {TMDB_IMAGES}" in csp  # posters come from TMDB's CDN
    assert "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp


def test_the_api_docs_page_works_without_the_csp(client: TestClient) -> None:
    response = client.get("/api/docs")

    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers  # it loads a CDN script
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_hsts_only_when_served_over_https(client: TestClient, settings: Settings) -> None:
    assert "Strict-Transport-Security" not in client.get("/api/health").headers

    https = create_app(settings.model_copy(update={"cookie_secure": True}))
    with TestClient(https) as https_client:
        hsts = https_client.get("/api/health").headers["Strict-Transport-Security"]

    assert hsts == "max-age=31536000; includeSubDomains"
