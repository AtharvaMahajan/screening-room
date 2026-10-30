"""Every failure returns {"error": {"code", "message"}} (project-structure.md §7).

Each test adds a small route to a real app that triggers one kind of failure.
"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from screening_room.config import Settings
from screening_room.core.errors import AppError
from screening_room.main import create_app

UNUSED_DATABASE_URL = "postgresql+psycopg://unused@localhost:1/unused"


class SignupIn(BaseModel):
    email: str
    password: str
    age: int


def build_app() -> FastAPI:
    app = create_app(Settings(database_url=UNUSED_DATABASE_URL))

    def raises_app_error() -> None:
        raise AppError(409, "email_taken", "That email is already registered.")

    def crashes() -> None:
        raise RuntimeError("internal detail: password=hunter2")

    def signup(body: SignupIn) -> None: ...

    app.add_api_route("/test/app-error", raises_app_error)
    app.add_api_route("/test/crash", crashes)
    app.add_api_route("/test/signup", signup, methods=["POST"])
    return app


@pytest.fixture
def client() -> TestClient:
    # raise_server_exceptions=False: respond with the 500 like production does,
    # instead of re-raising the crash inside the test.
    return TestClient(build_app(), raise_server_exceptions=False)


def test_app_error_uses_its_status_code_and_message(client: TestClient) -> None:
    response = client.get("/test/app-error")

    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "email_taken", "message": "That email is already registered."}
    }


def test_unknown_route_is_a_standard_404(client: TestClient) -> None:
    response = client.get("/api/no-such-route")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}


def test_wrong_method_is_a_standard_405_and_keeps_the_allow_header(client: TestClient) -> None:
    response = client.delete("/api/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert response.headers["allow"] == "GET"


def test_invalid_body_lists_each_failing_field(client: TestClient) -> None:
    response = client.post("/test/signup", json={"password": "hunter2", "age": "old"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert {detail["field"] for detail in error["details"]} == {"body.email", "body.age"}


def test_validation_errors_never_echo_submitted_values(client: TestClient) -> None:
    # Pydantic's raw errors include the input; a wrong-typed password would leak.
    response = client.post("/test/signup", json={"email": "a@b.c", "password": 12345, "age": 1})

    assert response.status_code == 422
    assert "12345" not in response.text


def test_unexpected_error_is_a_generic_500_and_is_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="screening_room.core.errors"):
        response = client.get("/test/crash")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "An unexpected error occurred."}
    }
    assert "hunter2" not in response.text  # nothing internal reaches the client...
    assert "hunter2" in caplog.text  # ...but the full error is logged for us


def test_openapi_documents_only_the_standard_error_format() -> None:
    schema = build_app().openapi()

    # FastAPI's own 422 schema would contradict what the API returns.
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    signup_responses = schema["paths"]["/test/signup"]["post"]["responses"]
    assert set(signup_responses) == {"200", "4XX", "5XX"}
    assert signup_responses["4XX"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorResponse"
    }
