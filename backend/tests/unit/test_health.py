"""Health endpoint behaviour, with the database Session replaced by a fake.

These run without PostgreSQL. The real-database path is covered in
tests/integration/test_health.py.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from screening_room.config import Settings
from screening_room.db import get_session
from screening_room.main import create_app

# Never connected to: SQLAlchemy engines connect lazily, and the session is faked.
UNUSED_DATABASE_URL = "postgresql+psycopg://unused:unused@localhost:1/unused"


class FakeSession:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.executed: list[str] = []

    def execute(self, statement: Any) -> None:
        self.executed.append(str(statement))
        if self.error is not None:
            raise self.error


def client_with_session(fake: FakeSession) -> TestClient:
    app = create_app(Settings(database_url=UNUSED_DATABASE_URL))

    def override() -> Iterator[FakeSession]:
        yield fake

    app.dependency_overrides[get_session] = override
    return TestClient(app)


def test_health_ok_when_database_responds() -> None:
    fake = FakeSession()
    response = client_with_session(fake).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert fake.executed == ["SELECT 1"]


def test_health_503_when_database_unreachable() -> None:
    error = OperationalError("SELECT 1", {}, Exception("password=secret host=db"))
    response = client_with_session(FakeSession(error=error)).get("/api/health")

    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "database_unavailable", "message": "The database is unavailable."}
    }
    # Connection details from the driver error must not leak to clients.
    assert "secret" not in response.text


@pytest.mark.parametrize("path", ["/api/docs", "/api/openapi.json"])
def test_api_docs_are_served_under_api_prefix(path: str) -> None:
    response = client_with_session(FakeSession()).get(path)
    assert response.status_code == 200
