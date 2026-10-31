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
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from screening_room.config import DatabaseSettings, Settings
from screening_room.db import create_db_engine, get_session
from screening_room.main import create_app
from screening_room.modules.catalog.models import IngestionRun, Person, Title
from screening_room.modules.profile.models import UserFavoriteTitle
from tests.conftest import make_test_settings

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@pytest.fixture(scope="session")
def database_url() -> str:
    # Only DATABASE_URL comes from the environment; every other setting is a
    # fixed test value (see make_test_settings).
    return DatabaseSettings().database_url


@pytest.fixture
def settings(database_url: str) -> Settings:
    """Overrides the root fixture: test settings, but with the real database."""
    return make_test_settings(database_url)


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    engine = create_db_engine(database_url)
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

    When a test writes setup data directly (e.g. to expire a session), it must
    call `db_session.commit()` too: the `client` fixture rolls back anything
    uncommitted after each request, just as production does.
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
def client(db_session: Session, settings: Settings) -> Iterator[TestClient]:
    """An API client whose requests all use the test's rolled-back session.

    Cookies persist between requests, like a browser's.
    """
    app = create_app(settings)

    def override_get_session() -> Iterator[Session]:
        yield db_session
        # The real get_session closes its session after each request, which
        # rolls back anything the request didn't commit (e.g. after a failed
        # insert). Here that rolls back to the last savepoint, so the next
        # request in the same test starts clean, as it would in production.
        db_session.rollback()

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def empty_catalog(db_session: Session) -> None:
    """Start from an EMPTY catalog, so tests that look at the whole pool aren't
    affected by your real one. Undone with the rest of the test's transaction."""
    db_session.execute(delete(UserFavoriteTitle))  # they reference titles (RESTRICT)
    db_session.execute(delete(Title))  # cascades to genres, credits, memberships, lists
    db_session.execute(delete(IngestionRun))
    db_session.execute(delete(Person))
    db_session.commit()  # releases a savepoint only
