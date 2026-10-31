"""TMDB JSON -> our types, against responses recorded from the real API
(tests/fixtures/tmdb/, refreshed with `python -m tests.fixtures.tmdb.record`).

Assertions use stable facts (names, dates, people), not values that drift
between recordings (vote counts, popularity).
"""

import copy
import importlib.util
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from screening_room.modules.catalog.providers.base import ProviderError, ProviderRef
from screening_room.modules.catalog.providers.tmdb import mapper

FIXTURES = Path(__file__).parents[1] / "fixtures" / "tmdb"
MIGRATION_0003 = (
    Path(__file__).parents[2] / "alembic/versions/0003_add_catalog_tables_and_genre_taxonomy.py"
)


def fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


# --- Movie details: Arrival (2016) ---------------------------------------------------------


@pytest.fixture(scope="module")
def arrival() -> dict[str, Any]:
    return fixture("movie_329865_arrival.json")


def test_movie_details(arrival: dict[str, Any]) -> None:
    details = mapper.title_details("movie", arrival)
    summary = details.summary

    assert summary.ref == ProviderRef("tmdb", "movie", 329865)
    assert summary.name == "Arrival"
    assert summary.original_language == "en"
    assert summary.release_date == date(2016, 11, 10)
    assert summary.provider_genre_ids == (18, 878, 9648)  # Drama, Sci-Fi, Mystery: TMDB order
    assert summary.vote_count and summary.vote_count > 0
    assert summary.poster_path and summary.poster_path.startswith("/")
    assert summary.adult is False
    assert details.runtime_minutes == 116
    assert details.imdb_id == "tt2543164"
    assert details.number_of_seasons is None  # movies never have seasons


def test_movie_credits_are_top_cast_plus_directors(arrival: dict[str, Any]) -> None:
    credits = mapper.title_details("movie", arrival).credits
    cast = [c for c in credits if c.role == "cast"]

    # TMDB lists 72 cast members; we keep the top-billed 10, in billing order.
    assert len(cast) == 10
    assert [c.order for c in cast] == list(range(10))
    assert (cast[0].name, cast[0].character_name) == ("Amy Adams", "Louise Banks")
    assert [(c.name, c.role) for c in credits if c.role != "cast"] == [
        ("Denis Villeneuve", "director")
    ]


def test_movie_recommendations_keep_tmdb_order(arrival: dict[str, Any]) -> None:
    recommendations = mapper.title_details("movie", arrival).recommendations

    assert len(recommendations) == 20  # page 1 of TMDB's list
    assert recommendations[0] == ProviderRef("tmdb", "movie", 2103)
    assert len(set(recommendations)) == len(recommendations)


# --- TV details: Breaking Bad --------------------------------------------------------------


@pytest.fixture(scope="module")
def breaking_bad() -> dict[str, Any]:
    return fixture("tv_1396_breaking_bad.json")


def test_tv_details_use_tv_field_names(breaking_bad: dict[str, Any]) -> None:
    details = mapper.title_details("tv", breaking_bad)

    assert details.summary.ref == ProviderRef("tmdb", "tv", 1396)
    assert details.summary.name == "Breaking Bad"  # "name", not "title"
    assert details.summary.release_date == date(2008, 1, 20)  # first_air_date
    assert details.summary.provider_genre_ids == (18, 80)
    assert details.number_of_seasons == 5
    # TMDB's episode_run_time is often empty for TV: runtime is genuinely unknown.
    assert breaking_bad["episode_run_time"] == []
    assert details.runtime_minutes is None
    assert details.imdb_id is None


def test_tv_credits_use_creators_instead_of_directors(breaking_bad: dict[str, Any]) -> None:
    credits = mapper.title_details("tv", breaking_bad).credits

    assert [(c.name, c.role) for c in credits if c.role != "cast"] == [
        ("Vince Gilligan", "creator")
    ]
    cast = [c for c in credits if c.role == "cast"]
    assert (cast[0].name, cast[0].character_name) == ("Bryan Cranston", "Walter White")
    assert len(cast) == 8  # fewer than 10 listed: keep them all


def test_tv_recommendations_are_tv_refs(breaking_bad: dict[str, Any]) -> None:
    recommendations = mapper.title_details("tv", breaking_bad).recommendations

    assert recommendations[0] == ProviderRef("tmdb", "tv", 60059)
    assert {ref.media_type for ref in recommendations} == {"tv"}


# --- List pages and genres -----------------------------------------------------------------


def test_list_page() -> None:
    page = mapper.list_page("movie", fixture("movie_popular_page1.json"))

    assert page.page == 1
    assert page.total_pages > 1
    assert len(page.results) == 20
    assert all(result.ref.media_type == "movie" for result in page.results)
    assert all(result.provider_genre_ids for result in page.results)  # from genre_ids


def test_discover_results_have_the_requested_genre() -> None:
    page = mapper.list_page("tv", fixture("tv_discover_scifi_page1.json"))

    assert all(10765 in result.provider_genre_ids for result in page.results)


def test_our_migration_maps_exactly_tmdbs_real_genres() -> None:
    """Closes the M2a gap: the genre IDs in migration 0003 match the live API."""
    spec = importlib.util.spec_from_file_location("migration_0003", MIGRATION_0003)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    for media_type in ("movie", "tv"):
        real = {g.id: g.name for g in mapper.genres(fixture(f"genres_{media_type}.json"))}
        ours = {gid: name for gid, (name, _) in migration.TMDB_GENRES[media_type].items()}
        assert ours == real, f"{media_type} genres differ from TMDB's"


# --- Messy and missing data ------------------------------------------------------------------


def test_missing_optional_fields_become_none(arrival: dict[str, Any]) -> None:
    data = copy.deepcopy(arrival)
    data.update(
        overview="",
        poster_path=None,
        release_date="",
        runtime=0,
        imdb_id="",
        vote_average=None,
    )
    del data["original_language"]
    del data["credits"]
    del data["recommendations"]

    details = mapper.title_details("movie", data)

    assert details.summary.overview is None
    assert details.summary.poster_path is None
    assert details.summary.release_date is None
    assert details.summary.original_language is None
    assert details.summary.vote_average is None
    assert details.runtime_minutes is None  # 0 means unknown, and the DB requires > 0
    assert details.imdb_id is None
    assert details.credits == ()
    assert details.recommendations == ()


def test_malformed_dates_become_none(arrival: dict[str, Any]) -> None:
    data = copy.deepcopy(arrival) | {"release_date": "2016-13-45"}

    assert mapper.title_summary("movie", data).release_date is None


@pytest.mark.parametrize("missing", ["id", "title"])
def test_missing_required_fields_are_an_error(arrival: dict[str, Any], missing: str) -> None:
    data = copy.deepcopy(arrival)
    del data[missing]

    with pytest.raises(ProviderError, match=missing):
        mapper.title_summary("movie", data)


def test_adult_and_non_title_recommendations_are_skipped() -> None:
    data = {
        "id": 1,
        "title": "Source",
        "recommendations": {
            "results": [
                {"id": 10, "media_type": "movie"},
                {"id": 11, "media_type": "movie", "adult": True},
                {"id": 12, "media_type": "person"},
                {"id": 13, "media_type": "tv"},
                {"id": 10, "media_type": "movie"},  # repeated: keeps its first rank
            ]
        },
    }

    assert mapper.title_details("movie", data).recommendations == (
        ProviderRef("tmdb", "movie", 10),
        ProviderRef("tmdb", "tv", 13),
    )


def test_someone_credited_twice_as_director_appears_once() -> None:
    director = {"id": 7, "name": "Co Director", "job": "Director"}
    data = {"id": 1, "title": "Source", "credits": {"cast": [], "crew": [director, director]}}

    credits = mapper.title_details("movie", data).credits

    assert [(c.person_provider_id, c.role) for c in credits] == [(7, "director")]


# --- Search -----------------------------------------------------------------------------------

# Hand-written: covers adult and malformed entries the recorded response doesn't have.
SEARCH_MULTI = {
    "page": 1,
    "results": [
        {
            "media_type": "movie",
            "id": 329865,
            "title": "Arrival",
            "release_date": "2016-11-10",
            "genre_ids": [18, 878],
            "adult": False,
            "vote_count": 20000,
        },
        {"media_type": "person", "id": 9827, "name": "Amy Adams", "adult": False},
        {
            "media_type": "tv",
            "id": 1396,
            "name": "Breaking Bad",
            "first_air_date": "2008-01-20",
            "genre_ids": [18, 80],
            "adult": False,
        },
        {"media_type": "movie", "id": 1, "title": "Adult film", "adult": True},
        {"media_type": "movie", "id": 2},  # malformed: no title
    ],
}


def test_search_keeps_movies_and_tv_and_drops_people_adult_and_broken_entries() -> None:
    results = mapper.search_results(SEARCH_MULTI)

    assert [(r.ref.media_type, r.ref.provider_id, r.name) for r in results] == [
        ("movie", 329865, "Arrival"),
        ("tv", 1396, "Breaking Bad"),
    ]
    assert results[1].release_date == date(2008, 1, 20)  # first_air_date for TV
    assert results[0].provider_genre_ids == (18, 878)


def test_recorded_search_drops_people_and_keeps_tmdb_order() -> None:
    data = fixture("search_multi_arrival.json")  # the real response for "arrival"
    people = [r for r in data["results"] if r["media_type"] == "person"]

    results = mapper.search_results(data)

    assert people  # the real response mixes in people...
    assert len(results) == len(data["results"]) - len(people)  # ...which are dropped
    assert (results[0].ref.provider_id, results[0].name) == (329865, "Arrival")
    assert results[0].provider_genre_ids  # from genre_ids
    assert any(r.release_date is None for r in results)  # "" means unknown, not an error
