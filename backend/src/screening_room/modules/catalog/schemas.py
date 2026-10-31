"""Catalog DTOs: API response models and the plain values other code passes around."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from screening_room.modules.catalog.providers.base import ProviderRef

# How current the returned metadata is (catalog-ingestion.md §11):
#   fresh:   fully hydrated within the TTL (or just refreshed)
#   stale:   full details, but older than the TTL and the provider couldn't refresh them
#   partial: only list-level fields; the provider couldn't supply the rest
MetadataStatus = Literal["fresh", "stale", "partial"]


# --- API models -----------------------------------------------------------------------


class GenreOut(BaseModel):
    id: int
    slug: str
    name: str


class TitleCardOut(BaseModel):
    """A title in a list: favorites, search results, later recommendations."""

    id: int
    media_type: Literal["movie", "tv"]
    name: str
    year: int | None
    poster_url: str | None


class CastMemberOut(BaseModel):
    name: str
    character: str | None
    profile_url: str | None


class TitleDetailOut(BaseModel):
    id: int
    media_type: Literal["movie", "tv"]
    name: str
    original_name: str | None
    overview: str | None
    release_date: date | None  # movie release, or TV first air date
    runtime_minutes: int | None  # movies; often unknown for TV
    number_of_seasons: int | None
    original_language: str | None
    vote_average: float | None
    vote_count: int | None
    poster_url: str | None
    backdrop_url: str | None
    genres: list[GenreOut]
    cast: list[CastMemberOut]  # top-billed, in billing order
    directors: list[str]  # movies
    creators: list[str]  # TV
    metadata_status: MetadataStatus


# --- Internal DTOs ----------------------------------------------------------------------


@dataclass(frozen=True)
class CastMember:
    name: str
    character: str | None
    profile_path: str | None


@dataclass(frozen=True)
class TitleRecord:
    """A title as stored, as plain values: safe to use after the transaction ends
    (project-structure.md §5.2)."""

    id: int
    ref: ProviderRef
    name: str
    original_name: str | None
    overview: str | None
    release_date: date | None
    runtime_minutes: int | None
    number_of_seasons: int | None
    original_language: str | None
    vote_average: float | None
    vote_count: int | None
    poster_path: str | None
    backdrop_path: str | None
    adult: bool
    detail_level: str
    details_synced_at: datetime | None
    genres: tuple[tuple[int, str, str], ...]  # (id, slug, name), in display order
    cast: tuple[CastMember, ...]
    directors: tuple[str, ...]
    creators: tuple[str, ...]


@dataclass(frozen=True)
class CandidateFeatures:
    """A candidate-pool title's features, for the recommender's retrieval."""

    title_id: int
    media_type: Literal["movie", "tv"]
    genre_ids: frozenset[int]
    runtime_minutes: int | None
    release_date: date | None
    vote_average: float | None
    vote_count: int | None
    popularity: float | None
    source_keys: frozenset[str]
