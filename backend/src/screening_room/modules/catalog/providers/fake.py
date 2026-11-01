"""A deterministic in-memory CatalogProvider for tests (ADR-0004).

Ingestion tests run against this instead of TMDB: same interface, no network,
the same answers every time, and failures on demand.
"""

from collections.abc import Iterable, Mapping
from math import ceil

from screening_room.modules.catalog.providers.base import (
    ListPage,
    ListQuery,
    MediaType,
    ProviderGenre,
    ProviderNotFoundError,
    ProviderRef,
    ProviderUnavailableError,
    TitleDetails,
    TitleSummary,
)


class FakeProvider:
    # Rows written from fake data look like TMDB rows (the schema allows only 'tmdb').
    name = "tmdb"

    def __init__(
        self,
        titles: Iterable[TitleDetails],
        genres: Mapping[MediaType, list[ProviderGenre]] | None = None,
        page_size: int = 20,
    ) -> None:
        self._details = {title.summary.ref: title for title in titles}
        self._genres = dict(genres or {})
        self._page_size = page_size
        self.missing: set[ProviderRef] = set()  # get_details -> ProviderNotFoundError
        self.failing: set[ProviderRef] = set()  # get_details -> ProviderUnavailableError
        self.search_failing = False  # search -> ProviderUnavailableError
        self.calls: list[tuple[str, object]] = []  # what was asked, in order

    def list_titles(self, query: ListQuery, page: int) -> ListPage:
        self.calls.append(("list_titles", (query, page)))
        matches = sorted(
            (t.summary for t in self._details.values() if _matches(t.summary, query)),
            # Like discover's vote_count.desc, with a stable tie-break.
            key=lambda s: (-(s.vote_count or 0), s.ref.provider_id),
        )
        start = (page - 1) * self._page_size
        return ListPage(
            page=page,
            total_pages=max(1, ceil(len(matches) / self._page_size)),
            results=tuple(matches[start : start + self._page_size]),
        )

    def get_details(self, ref: ProviderRef) -> TitleDetails:
        self.calls.append(("get_details", ref))
        if ref in self.failing:
            raise ProviderUnavailableError(f"fake outage for {ref}")
        if ref in self.missing or ref not in self._details:
            raise ProviderNotFoundError(f"no such title: {ref}")
        return self._details[ref]

    def list_genres(self, media_type: MediaType) -> list[ProviderGenre]:
        self.calls.append(("list_genres", media_type))
        return list(self._genres.get(media_type, []))

    def search(self, query: str, media_type: MediaType | None = None) -> list[TitleSummary]:
        """Case-insensitive substring match on the name, most-voted first."""
        self.calls.append(("search", (query, media_type)))
        if self.search_failing:
            raise ProviderUnavailableError("fake search outage")
        needle = query.casefold()
        return sorted(
            (
                t.summary
                for t in self._details.values()
                if needle in t.summary.name.casefold()
                and not t.summary.adult
                and media_type in (None, t.summary.ref.media_type)
            ),
            key=lambda s: (-(s.vote_count or 0), s.ref.provider_id),
        )


def _matches(summary: TitleSummary, query: ListQuery) -> bool:
    if summary.ref.media_type != query.media_type or summary.adult:
        return False
    params = query.params
    if "with_genres" in params and int(params["with_genres"]) not in summary.provider_genre_ids:
        return False
    if (
        "with_original_language" in params
        and summary.original_language != params["with_original_language"]
    ):
        return False
    return not (
        "vote_count.gte" in params and (summary.vote_count or 0) < int(params["vote_count.gte"])
    )


def fake_title(
    media_type: MediaType,
    provider_id: int,
    name: str = "",
    *,
    genre_ids: tuple[int, ...] = (),
    vote_count: int = 1000,
    original_language: str = "en",
    recommendations: tuple[ProviderRef, ...] = (),
) -> TitleDetails:
    """A small but complete TitleDetails for tests. To change other fields, use
    `dataclasses.replace(title, ...)` (the types are frozen dataclasses)."""
    ref = ProviderRef("tmdb", media_type, provider_id)
    summary = TitleSummary(
        ref=ref,
        name=name or f"{media_type.title()} {provider_id}",
        original_name=None,
        overview=None,
        original_language=original_language,
        release_date=None,
        poster_path=None,
        backdrop_path=None,
        popularity=1.0,
        vote_average=7.0,
        vote_count=vote_count,
        adult=False,
        provider_genre_ids=genre_ids,
    )
    return TitleDetails(
        summary=summary,
        imdb_id=None,
        runtime_minutes=100 if media_type == "movie" else None,
        number_of_seasons=None if media_type == "movie" else 1,
        credits=(),
        recommendations=recommendations,
    )
