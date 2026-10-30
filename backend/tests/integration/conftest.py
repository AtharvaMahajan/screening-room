"""Fixtures for tests that run against real PostgreSQL (project-structure.md §5.6).

The database is the one DATABASE_URL points at (the docker-compose database
locally, a service container in CI). Tests never leave data behind: everything
a test writes happens inside a transaction that is rolled back afterwards.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from screening_room.config import get_settings
from screening_room.db import create_db_engine, get_session
from screening_room.main import create_app

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    engine = create_db_engine(get_settings().database_url)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def _require_migrated_database(engine: Engine) -> None:
    """Fail fast with a clear message instead of confusing 'no such table' errors."""
    head = ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != head:
        pytest.fail(
            f"Test database is at migration {current!r}, expected {head!r}. "
            "Run `uv run alembic upgrade head` in backend/.",
            pytrace=False,
        )


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """A Session whose work is always rolled back at the end of the test.

    The test holds one connection with an outer transaction open. The Session
    joins it in "create_savepoint" mode, so when code under test calls
    `session.commit()` (as write handlers do), only a SAVEPOINT is released and
    nothing is really committed. Rolling back the outer transaction then
    undoes everything the test did.
    """
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,  # same as the app's session factory
    )
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """An API client whose requests all use the test's rolled-back session."""
    app = create_app()

    def override_get_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
