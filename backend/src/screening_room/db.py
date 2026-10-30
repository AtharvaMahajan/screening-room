"""Database engine, ORM base class and the per-request Session (ADR-0006).

Rules this module implements (project-structure.md §5.1):
- One Session per request.
- The Session is yielded *without* calling ``begin()``: SQLAlchemy autobegins a
  transaction on first use, and everything in the request shares it.
- ``close()`` always runs, which rolls back anything uncommitted and returns the
  connection to the pool. Handlers that write call ``session.commit()`` themselves.
"""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Initial values from ADR-0006, sized against AnyIO's 40-thread pool.
POOL_SIZE = 10
MAX_OVERFLOW = 10
# Fail fast when the database is unreachable instead of hanging a worker thread.
CONNECT_TIMEOUT_SECONDS = 5

# Deterministic constraint and index names (data-model.md §1). Without this,
# PostgreSQL picks names itself and Alembic can't reliably find a constraint
# again to alter or drop it in a later migration.
NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
}


class Base(DeclarativeBase):
    """Base class for every ORM model. Each module's models.py subclasses it."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_db_engine(database_url: str) -> Engine:
    return create_engine(
        database_url,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_pre_ping=True,  # transparently replace connections the server has dropped
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    # expire_on_commit=False lets handlers return data loaded before a commit.
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one Session per request, closed when the request ends."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_session)]


class PendingChangesError(RuntimeError):
    """Raised when ending a read transaction would silently discard changes."""


def end_read_transaction(session: Session) -> None:
    """End a read-only transaction and return its connection to the pool.

    Call this before waiting on an external service (e.g. TMDB), so the request
    doesn't hold a pooled connection or an open transaction while it waits
    (project-structure.md §5.2). The next database use autobegins a new
    transaction.

    Convert any ORM objects you still need into DTOs first: ending the
    transaction expires them.

    Only handlers and handler-level helpers may call this
    (tests/unit/test_transaction_boundaries.py enforces it).

    Limitation: changes that were already flushed (by an explicit ``flush()`` or
    autoflush) no longer appear as pending, so they can't be detected here and
    would be rolled back. Read paths don't flush, so this isn't a concern today.
    """
    if session.new or session.dirty or session.deleted:
        raise PendingChangesError(
            "end_read_transaction() called with unsaved changes; "
            "commit them first or this would discard them"
        )
    # Ending a transaction with no writes: rollback and commit are equivalent,
    # and rollback makes the read-only intent explicit.
    session.rollback()
