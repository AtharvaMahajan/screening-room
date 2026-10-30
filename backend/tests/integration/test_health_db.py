"""Health endpoint against the real PostgreSQL from docker-compose (or CI).

Requires DATABASE_URL (from the environment or the repo-root .env) to point at a
running database. Start one with `docker compose up -d db`.
"""

from fastapi.testclient import TestClient

from screening_room.main import create_app


def test_health_reports_real_database_ok() -> None:
    # `with` runs the lifespan, so the engine is disposed afterwards.
    with TestClient(create_app()) as client:
        response = client.get("/api/health")

    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "database": "ok"}
