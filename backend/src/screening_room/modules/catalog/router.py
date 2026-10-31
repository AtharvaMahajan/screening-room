"""Catalog endpoints. Readable by any signed-in user (security.md §6)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query

from screening_room.config import SettingsDep
from screening_room.core.errors import AppError
from screening_room.db import SessionDep
from screening_room.modules.catalog import read_through, service
from screening_room.modules.catalog.dependencies import CatalogProviderDep
from screening_room.modules.catalog.schemas import (
    GenreOut,
    SearchOut,
    TitleCardOut,
    TitleDetailOut,
)
from screening_room.modules.identity.dependencies import get_current_user

router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])

# Our ids are PostgreSQL bigints; anything outside that range can't exist.
TitleId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@router.get("/genres")
def list_genres(session: SessionDep) -> list[GenreOut]:
    """The genres people can like, avoid or filter by."""
    return service.selectable_genres(session)


@router.get("/titles")
def search_titles(
    session: SessionDep,
    settings: SettingsDep,
    q: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    media_type: Literal["movie", "tv"] | None = None,
    genre_ids: Annotated[list[int], Query(max_length=25)] = [],  # noqa: B006 (FastAPI copies it)
    limit: Annotated[int, Query(ge=1, le=service.SEARCH_LIMIT_MAX)] = 10,
) -> list[TitleCardOut]:
    """Search the local candidate pool by name; without `q`, suggest well-known
    titles in `genre_ids`. Never calls TMDB (catalog-ingestion.md §11)."""
    return service.search_pool_titles(
        session,
        query=q,
        media_type=media_type,
        genre_ids=genre_ids,
        limit=limit,
        image_base_url=settings.tmdb_image_base_url,
    )


@router.get("/titles/{title_id}")
def get_title(
    title_id: TitleId,
    session: SessionDep,
    provider: CatalogProviderDep,
    settings: SettingsDep,
) -> TitleDetailOut:
    # Read-only for fresh titles; the helper owns any refresh transactions.
    return read_through.get_title_detail(session, title_id, provider, settings)


@router.get("/search")
def search(
    session: SessionDep,
    provider: CatalogProviderDep,
    settings: SettingsDep,
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> SearchOut:
    """Search TMDB for movies and TV shows, beyond our candidate pool (FR-03).

    Results are stored as catalog rows (so they have ids and title pages) but
    don't become recommendable. Falls back to our own catalog if TMDB is down.
    """
    query = q.strip()
    if not query:
        raise AppError(422, "empty_query", "Type something to search for.")
    return read_through.search_titles(session, query, provider, settings.tmdb_image_base_url)
