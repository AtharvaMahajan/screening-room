"""Health endpoint: reports whether the API is up and can reach PostgreSQL.

It isn't part of any domain module (identity, catalog, ...), so it lives at the
package root rather than under ``modules/``.
"""

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from screening_room.db import SessionDep

router = APIRouter()


class HealthOut(BaseModel):
    status: Literal["ok", "unavailable"]
    database: Literal["ok", "unavailable"]


# `def`, not `async def`: the database call blocks, so FastAPI must run this
# handler in its thread pool (ADR-0006, project-structure.md §5.5).
@router.get(
    "/api/health",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthOut}},
)
def health(session: SessionDep, response: Response) -> HealthOut:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # Don't echo the exception: it can contain connection details.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthOut(status="unavailable", database="unavailable")
    # Read-only: no commit. The transaction ends when the session closes.
    return HealthOut(status="ok", database="ok")
