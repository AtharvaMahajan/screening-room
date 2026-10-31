"""Recommendation endpoint. Always for the signed-in user (security.md §6)."""

from fastapi import APIRouter, Depends

from screening_room.config import SettingsDep
from screening_room.db import SessionDep
from screening_room.modules.discovery import service
from screening_room.modules.discovery.schemas import RecommendationRequestIn, RecommendationsOut
from screening_room.modules.identity.dependencies import CurrentUserDep, get_current_user

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


@router.post("/recommendations")
def create_recommendations(
    body: RecommendationRequestIn,
    session: SessionDep,
    user: CurrentUserDep,
    settings: SettingsDep,
) -> RecommendationsOut:
    """A fresh, explained shortlist. POST because every call is logged (§15).

    Reads only the local database, never TMDB, so it carries the p95 < 1.5 s
    target (overview.md §7). The request and its results commit together.
    """
    result = service.recommend_for_user(session, user.id, body, settings.tmdb_image_base_url)
    session.commit()
    return result
