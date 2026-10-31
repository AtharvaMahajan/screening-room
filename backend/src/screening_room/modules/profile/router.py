"""Profile endpoints, under /api/me: always the signed-in user's own data (security.md §6)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from screening_room.config import SettingsDep
from screening_room.db import SessionDep
from screening_room.modules.identity.dependencies import CurrentUserDep, get_current_user
from screening_room.modules.profile import service
from screening_room.modules.profile.schemas import (
    FavoriteIn,
    FavoritesOut,
    PreferencesIn,
    PreferencesOut,
)

router = APIRouter(prefix="/api/me", dependencies=[Depends(get_current_user)])

TitleId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.get("/preferences")
def get_preferences(session: SessionDep, user: CurrentUserDep) -> PreferencesOut:
    return service.get_preferences(session, user.id)


@router.put("/preferences")
def put_preferences(
    body: PreferencesIn, session: SessionDep, user: CurrentUserDep
) -> PreferencesOut:
    result = service.replace_preferences(session, user.id, body)
    session.commit()
    return result


@router.get("/favorites")
def get_favorites(session: SessionDep, user: CurrentUserDep, settings: SettingsDep) -> FavoritesOut:
    return service.list_favorites(session, user.id, settings.tmdb_image_base_url)


@router.post("/favorites", status_code=status.HTTP_201_CREATED)
def add_favorite(
    body: FavoriteIn,
    response: Response,
    session: SessionDep,
    user: CurrentUserDep,
    settings: SettingsDep,
) -> FavoritesOut:
    """Add a favorite: 201 if new, 200 if it was already there. Returns the full list."""
    if service.add_favorite(session, user.id, body.title_id):
        session.commit()
    else:
        response.status_code = status.HTTP_200_OK
    return service.list_favorites(session, user.id, settings.tmdb_image_base_url)


@router.delete("/favorites/{title_id}")
def remove_favorite(
    title_id: TitleId, session: SessionDep, user: CurrentUserDep, settings: SettingsDep
) -> FavoritesOut:
    """Remove a favorite (idempotent). Returns the full list."""
    service.remove_favorite(session, user.id, title_id)
    session.commit()
    return service.list_favorites(session, user.id, settings.tmdb_image_base_url)
