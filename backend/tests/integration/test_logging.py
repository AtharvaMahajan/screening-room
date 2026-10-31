"""Request and event logs through the real app (M5b), including what must never
appear in them (security.md §9)."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from screening_room.config import Settings
from tests.integration.helpers import PASSWORD, add_candidate, login, register, send

EMAIL = "logged@example.com"


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """For every test here: one registration per IP, so the rate-limit test can trip it.
    Each test registers at most once."""
    return settings.model_copy(update={"registrations_per_ip": 1})


def records(caplog: pytest.LogCaptureFixture, msg: str) -> list[dict[str, object]]:
    """The context and fields of every captured record with this message."""
    return [
        {**getattr(r, "context", {}), **getattr(r, "fields", {}), "level": r.levelname}
        for r in caplog.records
        if r.getMessage() == msg
    ]


def everything_logged(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(
        f"{r.getMessage()} {getattr(r, 'context', {})} {getattr(r, 'fields', {})}"
        for r in caplog.records
    )


def test_each_request_is_one_line_with_an_id(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")

    response = client.get("/api/titles/123456789012", params={"q": "ignored"})

    [line] = records(caplog, "request")
    assert line["request_id"] == response.headers["X-Request-ID"]
    assert {k: line[k] for k in ("method", "path", "route", "status")} == {
        "method": "GET",
        "path": "/api/titles/123456789012",  # never the query string
        "route": "/api/titles/{title_id}",  # for grouping
        "status": 401,
    }
    assert isinstance(line["duration_ms"], float)


def test_a_valid_incoming_request_id_is_kept_and_a_strange_one_replaced(
    client: TestClient,
) -> None:
    kept = client.get("/api/health", headers={"X-Request-ID": "from-proxy-1234"})
    replaced = client.get("/api/health", headers={"X-Request-ID": "<script>"})

    assert kept.headers["X-Request-ID"] == "from-proxy-1234"
    assert replaced.headers["X-Request-ID"] != "<script>"


def test_signed_in_requests_carry_the_user_id_but_never_the_email_or_password(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("DEBUG")
    assert register(client, email=EMAIL).status_code == 201
    assert login(client, EMAIL).status_code == 200

    client.get("/api/me/favorites")

    favorites = [r for r in records(caplog, "request") if r["path"] == "/api/me/favorites"]
    assert isinstance(favorites[0]["user_id"], int)
    logged = everything_logged(caplog)
    assert EMAIL not in logged
    assert PASSWORD not in logged
    assert "sr_session" not in logged


def test_search_text_is_never_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG")
    register(client, email=EMAIL)

    client.get("/api/search", params={"q": "embarrassing guilty pleasure"})

    assert "embarrassing" not in everything_logged(caplog)


def test_recommendations_and_result_actions_are_logged_with_the_request_id(
    client: TestClient,
    db_session: Session,
    empty_catalog: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    for name in ("Logged A", "Logged B", "Logged C"):
        add_candidate(db_session, name, release_date=date(2016, 1, 1))
    token = register(client, email=EMAIL).json()["csrf_token"]

    shortlist = send(client, "POST", "/api/recommendations", {"limit": 3}, csrf_token=token)
    result_id = shortlist.json()["results"][0]["result_id"]
    send(
        client,
        "POST",
        f"/api/recommendations/results/{result_id}/events",
        {"type": "saved"},
        csrf_token=token,
    )

    [served] = records(caplog, "recommendations served")
    assert served["request_id"] == shortlist.headers["X-Request-ID"]
    assert isinstance(served["latency_ms"], int)
    assert (served["results"], served["cold_start"]) == (3, True)
    [action] = records(caplog, "result event")
    assert (action["event"], action["result_id"]) == ("saved", result_id)


def test_rate_limits_are_logged_by_policy_only(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    register(client, email="first@example.com")

    register(client, email="second@example.com")

    [limited] = records(caplog, "rate limited")
    assert (limited["policy"], limited["level"]) == ("registration_per_ip", "WARNING")
    assert "second@example.com" not in everything_logged(caplog)


def test_a_crash_is_logged_as_an_error_with_status_500(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    app = client.app
    assert isinstance(app, FastAPI)

    @app.get("/api/test-crash")
    def crash() -> None:
        raise RuntimeError("bug")

    caplog.set_level("INFO")
    with TestClient(app, raise_server_exceptions=False) as crashing:
        response = crashing.get("/api/test-crash")

    assert response.status_code == 500
    [line] = [r for r in records(caplog, "request") if r["path"] == "/api/test-crash"]
    assert (line["status"], line["level"]) == (500, "ERROR")
    assert "request_id" in line
