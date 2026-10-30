"""Health endpoint: reports whether the API is up and can reach PostgreSQL.

It isn't part of any domain module (identity, catalog, ...), so it lives at the
package root rather than under ``modules/``.
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from screening_room.core.errors import AppError
from screening_room.db import SessionDep

router = APIRouter()


class HealthOut(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]


# `def`, not `async def`: the database call blocks, so FastAPI must run this
# handler in its thread pool (ADR-0006, project-structure.md §5.5).
@router.get("/api/health")
def health(session: SessionDep) -> HealthOut:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # `from None` drops the driver error, which can contain connection details;
        # the client only ever sees the code and message below.
        raise AppError(503, "database_unavailable", "The database is unavailable.") from None
    # Read-only: no commit. The transaction ends when the session closes.
    return HealthOut(status="ok", database="ok")
