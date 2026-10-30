"""Session and transaction behaviour against real PostgreSQL (ADR-0006)."""

from fastapi.testclient import TestClient
from sqlalchemy import Engine, QueuePool, text
from sqlalchemy.orm import Session

from screening_room.db import create_db_engine, create_session_factory, end_read_transaction


def test_end_read_transaction_returns_the_connection_to_the_pool(database_url: str) -> None:
    # A dedicated engine, so the pool count isn't affected by other fixtures.
    engine = create_db_engine(database_url)
    assert isinstance(engine.pool, QueuePool)
    session = create_session_factory(engine)()
    try:
        session.execute(text("SELECT 1"))  # autobegins a transaction
        assert session.in_transaction()
        assert engine.pool.checkedout() == 1

        end_read_transaction(session)

        assert not session.in_transaction()
        assert engine.pool.checkedout() == 0, "connection should be back in the pool"

        session.execute(text("SELECT 1"))  # the next use autobegins a fresh transaction
        assert session.in_transaction()
    finally:
        session.close()
        engine.dispose()


def test_commits_inside_a_test_are_never_really_committed(
    db_session: Session, engine: Engine
) -> None:
    db_session.execute(text("CREATE TABLE fixture_probe (id integer)"))
    db_session.execute(text("INSERT INTO fixture_probe VALUES (1)"))
    db_session.commit()  # what a write handler does: here it only releases a savepoint

    # The test's session still sees its own write after the "commit"...
    assert db_session.execute(text("SELECT count(*) FROM fixture_probe")).scalar_one() == 1

    # ...but no other connection can, because the outer transaction is still
    # open. The db_session fixture rolls it back when the test ends.
    with engine.connect() as other:
        assert other.execute(text("SELECT to_regclass('fixture_probe')")).scalar_one() is None


def test_client_fixture_serves_api_requests(client: TestClient) -> None:
    # Smoke test for the fixture. Proving that requests really use db_session
    # needs an endpoint that writes, which arrives with the first tables.
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
