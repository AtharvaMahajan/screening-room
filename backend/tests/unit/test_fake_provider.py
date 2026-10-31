"""The FakeProvider that ingestion tests (M2c) will run against."""

import pytest

from screening_room.config import Settings
from screening_room.modules.catalog.providers.base import (
    CatalogProvider,
    ListQuery,
    ProviderGenre,
    ProviderNotFoundError,
    ProviderRef,
    ProviderUnavailableError,
)
from screening_room.modules.catalog.providers.fake import FakeProvider, fake_title
from screening_room.modules.catalog.providers.tmdb.client import TmdbClient
from screening_room.modules.catalog.providers.tmdb.provider import TmdbProvider

SCIFI = 878


TITLES = [
    fake_title("movie", 1, "Low votes", genre_ids=(SCIFI,), vote_count=10),
    fake_title("movie", 2, "Popular sci-fi", genre_ids=(SCIFI,), vote_count=900),
    fake_title("movie", 3, "Drama", genre_ids=(18,), vote_count=500),
    fake_title("movie", 4, "French", vote_count=300, original_language="fr"),
    fake_title("tv", 1, "A show", vote_count=800),  # same ID, other media type
]


def make_provider(page_size: int = 2) -> FakeProvider:
    return FakeProvider(
        TITLES,
        genres={"movie": [ProviderGenre(SCIFI, "Science Fiction")]},
        page_size=page_size,
    )


def names(provider: FakeProvider, query: ListQuery, page: int = 1) -> list[str]:
    return [summary.name for summary in provider.list_titles(query, page).results]


def test_both_providers_implement_the_interface() -> None:
    # Checked by mypy: these assignments fail type-checking if either drifts.
    client = TmdbClient("unused-token")
    try:
        fake: CatalogProvider = make_provider()
        real: CatalogProvider = TmdbProvider(client)
        assert fake.name == real.name == "tmdb"
    finally:
        client.close()


def test_lists_are_sorted_by_votes_and_paged() -> None:
    provider = make_provider()
    query = ListQuery("movie", "discover")

    assert names(provider, query, page=1) == ["Popular sci-fi", "Drama"]
    assert names(provider, query, page=2) == ["French", "Low votes"]
    assert provider.list_titles(query, 1).total_pages == 2


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"with_genres": SCIFI}, ["Popular sci-fi", "Low votes"]),
        ({"with_original_language": "fr"}, ["French"]),
        ({"with_genres": SCIFI, "vote_count.gte": 100}, ["Popular sci-fi"]),
    ],
)
def test_list_filters(params: dict[str, str | int], expected: list[str]) -> None:
    provider = make_provider(page_size=20)

    assert names(provider, ListQuery("movie", "discover", params)) == expected


def test_details_and_injected_failures() -> None:
    provider = make_provider()
    movie, show = ProviderRef("tmdb", "movie", 1), ProviderRef("tmdb", "tv", 1)

    assert provider.get_details(show).summary.name == "A show"

    provider.failing.add(movie)
    with pytest.raises(ProviderUnavailableError):
        provider.get_details(movie)

    provider.missing.add(show)
    with pytest.raises(ProviderNotFoundError):
        provider.get_details(show)

    with pytest.raises(ProviderNotFoundError):
        provider.get_details(ProviderRef("tmdb", "movie", 999))


def test_calls_are_recorded_in_order() -> None:
    provider = make_provider()
    ref = ProviderRef("tmdb", "movie", 2)

    provider.list_genres("movie")
    provider.get_details(ref)

    assert provider.calls == [("list_genres", "movie"), ("get_details", ref)]


def test_tmdb_token_is_optional_but_required_where_used(settings: Settings) -> None:
    assert settings.tmdb_api_token is None  # the web app starts without it

    with pytest.raises(RuntimeError, match="TMDB_API_TOKEN"):
        settings.require_tmdb_token()
