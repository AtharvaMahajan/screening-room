"""Library endpoints, under /api/me: always the signed-in user's own rows (security.md §6).

Every change returns the title's whole library state, so the UI can update all
its buttons from one response. The list routes serve the Library page (FR-12).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from screening_room.config import SettingsDep
from screening_room.db import SessionDep
from screening_room.modules.identity.dependencies import CurrentUserDep, get_current_user
from screening_room.modules.library import service
from screening_room.modules.library.schemas import (
    NotForMeOut,
    RatingIn,
    RatingOut,
    TitleStateOut,
    ViewingIn,
    ViewingOut,
    WatchlistItemOut,
)

router = APIRouter(prefix="/api/me", dependencies=[Depends(get_current_user)])

TitleId = Annotated[int, Path(ge=1, le=2**63 - 1)]
MediaTypeFilter = Annotated[Literal["movie", "tv"] | None, Query()]
Limit = Annotated[int, Query(ge=1, le=service.LIST_LIMIT_MAX)]


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


# --- Lists (FR-12): newest first, optionally only movies or only TV ------------------------


@router.get("/watchlist")
def list_watchlist(
    session: SessionDep,
    user: CurrentUserDep,
    settings: SettingsDep,
    media_type: MediaTypeFilter = None,
    limit: Limit = 100,
) -> list[WatchlistItemOut]:
    return service.watchlist(session, user.id, media_type, limit, settings.tmdb_image_base_url)


@router.get("/history")
def list_history(
    session: SessionDep,
    user: CurrentUserDep,
    settings: SettingsDep,
    media_type: MediaTypeFilter = None,
    limit: Limit = 100,
) -> list[ViewingOut]:
    """Every viewing, so a rewatch appears again."""
    return service.history(session, user.id, media_type, limit, settings.tmdb_image_base_url)


@router.get("/ratings")
def list_ratings(
    session: SessionDep,
    user: CurrentUserDep,
    settings: SettingsDep,
    media_type: MediaTypeFilter = None,
    limit: Limit = 100,
) -> list[RatingOut]:
    return service.ratings(session, user.id, media_type, limit, settings.tmdb_image_base_url)


@router.get("/not-for-me")
def list_not_for_me(
    session: SessionDep,
    user: CurrentUserDep,
    settings: SettingsDep,
    media_type: MediaTypeFilter = None,
    limit: Limit = 100,
) -> list[NotForMeOut]:
    """Titles you turned down, so you can undo any of them."""
    return service.not_for_me_list(
        session, user.id, media_type, limit, settings.tmdb_image_base_url
    )
