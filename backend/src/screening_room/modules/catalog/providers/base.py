"""The provider interface and the provider-neutral types it returns (ADR-0004).

These are plain frozen values (no ORM, no HTTP), so they can cross threads and
transaction boundaries safely (project-structure.md §5.2).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

MediaType = Literal["movie", "tv"]
CreditRole = Literal["cast", "director", "creator", "writer"]
ListEndpoint = Literal["popular", "top_rated", "discover"]


@dataclass(frozen=True)
class ProviderRef:
    """A title's identity at a provider. TMDB IDs are only unique per media type."""

    provider: str
    media_type: MediaType
    provider_id: int


@dataclass(frozen=True)
class TitleSummary:
    """What list endpoints return: enough for a `summary` catalog row."""

    ref: ProviderRef
    name: str
    original_name: str | None
    overview: str | None
    original_language: str | None
    release_date: date | None  # movie release date, or TV first air date
    poster_path: str | None
    backdrop_path: str | None
    popularity: float | None
    vote_average: float | None
    vote_count: int | None
    adult: bool
    provider_genre_ids: tuple[int, ...]  # in provider order


@dataclass(frozen=True)
class Credit:
    person_provider_id: int
    name: str
    profile_path: str | None
    role: CreditRole
    character_name: str | None
    order: int


@dataclass(frozen=True)
class TitleDetails:
    """A full hydration: details, credits and the provider's recommendation list."""

    summary: TitleSummary
    imdb_id: str | None
    runtime_minutes: int | None  # movies; typical episode length for TV, when known
    number_of_seasons: int | None  # TV only
    credits: tuple[Credit, ...]
    # The provider's "recommended" titles, best first (rank = position + 1).
    recommendations: tuple[ProviderRef, ...]


@dataclass(frozen=True)
class ListQuery:
    """One list request, e.g. popular movies or a genre's discover list."""

    media_type: MediaType
    endpoint: ListEndpoint
    params: Mapping[str, str | int] = field(default_factory=dict)


@dataclass(frozen=True)
class ListPage:
    page: int
    total_pages: int
    results: tuple[TitleSummary, ...]


@dataclass(frozen=True)
class ProviderGenre:
    id: int
    name: str


# --- Errors ------------------------------------------------------------------------


class ProviderError(Exception):
    """Any failure talking to a provider."""


class ProviderNotFoundError(ProviderError):
    """The provider has no such title (HTTP 404): mark it `missing`, keep going."""


class ProviderAuthError(ProviderError):
    """Bad or missing credentials (HTTP 401/403): stop the whole run."""


class ProviderUnavailableError(ProviderError):
    """Timeouts, connection errors, 5xx or 429 after all retries: try again later."""


# --- The interface -------------------------------------------------------------------


class CatalogProvider(Protocol):
    """What the catalog needs from a metadata provider."""

    name: str

    def list_titles(self, query: ListQuery, page: int) -> ListPage: ...

    def get_details(self, ref: ProviderRef) -> TitleDetails: ...

    def list_genres(self, media_type: MediaType) -> list[ProviderGenre]: ...

    def search(self, query: str) -> list[TitleSummary]:
        """Movies and TV shows matching `query`, best match first. No adult titles."""
        ...
