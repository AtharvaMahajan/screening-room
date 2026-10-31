"""Recommendation endpoints. Always for the signed-in user (security.md §6)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from screening_room.config import SettingsDep
from screening_room.db import SessionDep
from screening_room.modules.discovery import service
from screening_room.modules.discovery.schemas import (
    RecommendationRequestIn,
    RecommendationsOut,
    ResultEventIn,
)
from screening_room.modules.identity.dependencies import CurrentUserDep, get_current_user
from screening_room.modules.library import service as library
from screening_room.modules.library.schemas import TitleStateOut

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])

ResultId = Annotated[int, Path(ge=1, le=2**63 - 1)]


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


@router.post("/recommendations/results/{result_id}/events", status_code=status.HTTP_201_CREATED)
def record_result_event(
    result_id: ResultId, body: ResultEventIn, session: SessionDep, user: CurrentUserDep
) -> TitleStateOut:
    """Save, watch, rate, dismiss, skip or open a recommendation (FR-11).

    One transaction: the library change and the event commit together
    (overview.md §6.4). Returns the title's library state for the buttons.
    """
    title_id = service.record_result_event(session, user.id, result_id, body)
    session.commit()
    return library.title_state(session, user.id, title_id)
