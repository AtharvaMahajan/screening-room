"""Database engine and the per-request Session dependency (ADR-0006).

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
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

# Initial values from ADR-0006, sized against AnyIO's 40-thread pool.
POOL_SIZE = 10
MAX_OVERFLOW = 10
# Fail fast when the database is unreachable instead of hanging a worker thread.
CONNECT_TIMEOUT_SECONDS = 5


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
