"""Local pool search and suggestions (GET /api/titles) and the genre list (GET /api/genres).

These start from an EMPTY catalog (conftest.py), so results are exactly the
titles each test adds.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from screening_room.modules.catalog.models import Title
from tests.integration.helpers import add_candidate, genre_id, register


@pytest.fixture
def api(client: TestClient, empty_catalog: None) -> TestClient:
    assert register(client, email="search@example.com").status_code == 201
    return client


def names(client: TestClient, **params: str | int) -> list[str]:
    response = client.get("/api/titles", params=params)
    assert response.status_code == 200, response.text
    return [card["name"] for card in response.json()]


# --- Genres --------------------------------------------------------------------------------


def test_genre_list_has_the_22_selectable_genres(api: TestClient) -> None:
    genres = api.get("/api/genres").json()
    slugs = [genre["slug"] for genre in genres]

    assert len(genres) == 22
    assert {"news", "talk", "tv-movie"}.isdisjoint(slugs)
    assert {"kids", "reality", "science-fiction"} <= set(slugs)
    assert [g["name"] for g in genres] == sorted(g["name"] for g in genres)  # alphabetical


# --- Search ----------------------------------------------------------------------------------


def test_search_is_case_insensitive_and_puts_prefix_matches_first(
    api: TestClient, db_session: Session
) -> None:
    add_candidate(db_session, "The Godfather", vote_count=9000)
    add_candidate(db_session, "God's Own Country", vote_count=100)
    add_candidate(db_session, "Arrival", vote_count=5000)

    # "God's..." starts with the query, so it beats the more-voted "The Godfather".
    assert names(api, q="god") == ["God's Own Country", "The Godfather"]


def test_search_matches_the_original_name(api: TestClient, db_session: Session) -> None:
    add_candidate(db_session, "Spirited Away", original_name="千と千尋の神隠し")

    assert names(api, q="千尋") == ["Spirited Away"]


@pytest.mark.parametrize("wildcard", ["%", "_"])
def test_like_wildcards_in_the_query_match_literally(
    api: TestClient, db_session: Session, wildcard: str
) -> None:
    add_candidate(db_session, "Anything")

    assert names(api, q=wildcard) == []  # not "everything"


def test_search_filters_by_media_type(api: TestClient, db_session: Session) -> None:
    add_candidate(db_session, "Dark", media_type="tv")
    add_candidate(db_session, "Dark City", media_type="movie")

    assert names(api, q="dark", media_type="tv") == ["Dark"]


def test_search_only_returns_candidate_pool_titles(api: TestClient, db_session: Session) -> None:
    add_candidate(db_session, "Pool Kept")
    hidden: list[tuple[str, dict[str, Any]]] = [
        ("Pool Missing", {"provider_status": "missing"}),
        ("Pool Adult", {"adult": True}),
        ("Pool Summary", {"detail_level": "summary", "details_synced_at": None}),
    ]
    for name, values in hidden:
        title_id = add_candidate(db_session, name)
        db_session.execute(update(Title).where(Title.id == title_id).values(**values))
    db_session.commit()

    assert names(api, q="pool") == ["Pool Kept"]


# --- Suggestions (no query) -----------------------------------------------------------------


def test_suggestions_are_well_known_titles_in_the_chosen_genres(
    api: TestClient, db_session: Session
) -> None:
    add_candidate(db_session, "Big Comedy", genre_ids=(35,), vote_count=9000)
    add_candidate(db_session, "Small Comedy", genre_ids=(35,), vote_count=10)
    add_candidate(db_session, "Big Horror", genre_ids=(27,), vote_count=9999)

    comedy = genre_id(db_session, "comedy")

    assert names(api, genre_ids=comedy) == ["Big Comedy", "Small Comedy"]
    assert names(api, genre_ids=comedy, limit=1) == ["Big Comedy"]


def test_search_limits_are_enforced(api: TestClient) -> None:
    assert api.get("/api/titles", params={"limit": 21}).status_code == 422
    assert api.get("/api/titles", params={"q": "x" * 101}).status_code == 422


def test_search_needs_sign_in(client: TestClient) -> None:
    assert client.get("/api/titles", params={"q": "god"}).status_code == 401
    assert client.get("/api/genres").status_code == 401
