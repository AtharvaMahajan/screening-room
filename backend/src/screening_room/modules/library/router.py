"""Library endpoints, under /api/me: always the signed-in user's own rows (security.md §6).

Every route returns the title's whole library state, so the UI can update all
its buttons from one response.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from screening_room.db import SessionDep
from screening_room.modules.identity.dependencies import CurrentUserDep, get_current_user
from screening_room.modules.library import service
from screening_room.modules.library.schemas import RatingIn, TitleStateOut, ViewingIn

router = APIRouter(prefix="/api/me", dependencies=[Depends(get_current_user)])

TitleId = Annotated[int, Path(ge=1, le=2**63 - 1)]


def _commit_and_return(session: Session, user_id: int, title_id: int) -> TitleStateOut:
    session.commit()
    return service.title_state(session, user_id, title_id)


@router.get("/titles/{title_id}")
def get_title_state(title_id: TitleId, session: SessionDep, user: CurrentUserDep) -> TitleStateOut:
    """What you've recorded about this title: watchlist, viewings, rating, not for me."""
    service.require_title(session, title_id)
    return service.title_state(session, user.id, title_id)


@router.put("/watchlist/{title_id}")
def add_to_watchlist(title_id: TitleId, session: SessionDep, user: CurrentUserDep) -> TitleStateOut:
    """Save for later (idempotent)."""
    service.add_to_watchlist(session, user.id, title_id)
    return _commit_and_return(session, user.id, title_id)


@router.delete("/watchlist/{title_id}")
def remove_from_watchlist(
    title_id: TitleId, session: SessionDep, user: CurrentUserDep
) -> TitleStateOut:
    service.require_title(session, title_id)
    service.remove_from_watchlist(session, user.id, title_id)
    return _commit_and_return(session, user.id, title_id)


@router.post("/history/{title_id}", status_code=status.HTTP_201_CREATED)
def mark_watched(
    title_id: TitleId, body: ViewingIn, session: SessionDep, user: CurrentUserDep
) -> TitleStateOut:
    """Record a viewing; doing it again records a rewatch. Takes it off the watchlist."""
    service.mark_watched(session, user.id, title_id, body.watched_on)
    return _commit_and_return(session, user.id, title_id)


@router.delete("/history/{title_id}")
def unmark_watched(title_id: TitleId, session: SessionDep, user: CurrentUserDep) -> TitleStateOut:
    """Remove every viewing of this title (a rating stays)."""
    service.require_title(session, title_id)
    service.unmark_watched(session, user.id, title_id)
    return _commit_and_return(session, user.id, title_id)


@router.put("/ratings/{title_id}")
def rate(
    title_id: TitleId, body: RatingIn, session: SessionDep, user: CurrentUserDep
) -> TitleStateOut:
    """Rate 1-5★. Rating something you haven't marked watched marks it watched."""
    service.rate(session, user.id, title_id, body.value)
    return _commit_and_return(session, user.id, title_id)


@router.delete("/ratings/{title_id}")
def remove_rating(title_id: TitleId, session: SessionDep, user: CurrentUserDep) -> TitleStateOut:
    service.require_title(session, title_id)
    service.remove_rating(session, user.id, title_id)
    return _commit_and_return(session, user.id, title_id)


@router.put("/not-for-me/{title_id}")
def mark_not_for_me(title_id: TitleId, session: SessionDep, user: CurrentUserDep) -> TitleStateOut:
    """Never recommend this title (until undone)."""
    service.mark_not_for_me(session, user.id, title_id)
    return _commit_and_return(session, user.id, title_id)


@router.delete("/not-for-me/{title_id}")
def undo_not_for_me(title_id: TitleId, session: SessionDep, user: CurrentUserDep) -> TitleStateOut:
    service.require_title(session, title_id)
    service.undo_not_for_me(session, user.id, title_id)
    return _commit_and_return(session, user.id, title_id)
