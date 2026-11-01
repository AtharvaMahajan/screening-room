"""TMDB search and favorites found through it (catalog-ingestion.md §11, overview.md §6.3).

TMDB is replaced by a FakeProvider through FastAPI's dependency override. Its
names are unique per test run, so the real catalog in the dev database doesn't
interfere.
"""

from collections.abc import Iterator
from dataclasses import replace
from itertools import count
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from screening_room.modules.catalog.dependencies import get_catalog_provider
from screening_room.modules.catalog.models import (
    CandidatePoolMembership,
    ProviderTitleRecommendation,
    Title,
)
from screening_room.modules.catalog.providers.base import (
    MediaType,
    ProviderRef,
    TitleDetails,
    TitleSummary,
)
from screening_room.modules.catalog.providers.fake import FakeProvider, fake_title
from tests.integration.helpers import add_candidate, register, send

_ids = count(960_000_000)


class WatchedProvider(FakeProvider):
    """Fails the test if TMDB is called while a transaction is open (ADR-0006)."""

    def __init__(self, titles: list[TitleDetails], session: Session) -> None:
        super().__init__(titles)
        self._session = session

    def search(self, query: str, media_type: MediaType | None = None) -> list[TitleSummary]:
        assert not self._session.in_transaction(), "TMDB called with a transaction open"
        return super().search(query, media_type)

    def get_details(self, ref: ProviderRef) -> TitleDetails:
        assert not self._session.in_transaction(), "TMDB called with a transaction open"
        return super().get_details(ref)


@pytest.fixture
def word() -> str:
    """A made-up word, so search results come only from this test's titles."""
    return f"zq{uuid4().hex[:8]}"


@pytest.fixture
def tmdb(word: str, db_session: Session) -> WatchedProvider:
    titles = [
        fake_title("movie", next(_ids), f"{word} Odyssey", genre_ids=(878,), vote_count=900),
        fake_title("tv", next(_ids), f"The {word} Files", genre_ids=(18,), vote_count=500),
    ]
    neighbor = fake_title("movie", next(_ids), f"{word} Returns", vote_count=10)
    titles[0] = replace(titles[0], recommendations=(neighbor.summary.ref,))
    return WatchedProvider([*titles, neighbor], db_session)


@pytest.fixture
def api(client: TestClient, tmdb: FakeProvider | None) -> Iterator[TestClient]:
    assert register(client, email="searcher@example.com").status_code == 201
    use_provider(client, tmdb)
    yield client


def use_provider(client: TestClient, provider: FakeProvider | None) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_catalog_provider] = lambda: provider


def search(client: TestClient, q: str) -> dict[str, Any]:
    response = client.get("/api/search", params={"q": q})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def result_names(body: dict[str, Any]) -> list[str]:
    return [r["name"] for r in body["results"]]


# --- Search ---------------------------------------------------------------------------------


def test_search_returns_tmdb_results_as_catalog_titles_outside_the_pool(
    api: TestClient, word: str, db_session: Session
) -> None:
    body = search(api, word)

    assert body["source"] == "tmdb"
    assert result_names(body) == [f"{word} Odyssey", f"The {word} Files", f"{word} Returns"]
    titles = db_session.scalars(select(Title).where(Title.name.contains(word))).all()
    assert {t.detail_level for t in titles} == {"summary"}  # stored, but only the summary
    in_pool = db_session.scalars(
        select(CandidatePoolMembership).where(
            CandidatePoolMembership.title_id.in_([t.id for t in titles])
        )
    ).all()
    assert in_pool == []  # search never makes a title recommendable


def test_searching_again_reuses_the_same_titles(api: TestClient, word: str) -> None:
    first = search(api, word)["results"]
    again = search(api, word)["results"]

    assert first == again  # same ids: an idempotent cache fill


def test_when_tmdb_is_down_search_falls_back_to_our_catalog(
    api: TestClient, tmdb: FakeProvider, word: str, db_session: Session
) -> None:
    add_candidate(db_session, f"{word} Local Classic")
    tmdb.search_failing = True

    body = search(api, word)

    assert body["source"] == "local"
    assert result_names(body) == [f"{word} Local Classic"]


@pytest.mark.parametrize("tmdb", [None])
def test_without_a_tmdb_token_search_is_local(
    api: TestClient, word: str, db_session: Session
) -> None:
    add_candidate(db_session, f"{word} Pool Title")

    body = search(api, word)

    assert (body["source"], result_names(body)) == ("local", [f"{word} Pool Title"])


@pytest.mark.parametrize(
    ("media_type", "expected"),
    [("movie", ["{w} Odyssey", "{w} Returns"]), ("tv", ["The {w} Files"])],
)
def test_search_can_ask_for_movies_or_tv_only(
    api: TestClient, tmdb: FakeProvider, word: str, media_type: str, expected: list[str]
) -> None:
    response = api.get("/api/search", params={"q": word, "media_type": media_type})

    assert response.status_code == 200, response.text
    assert result_names(response.json()) == [name.format(w=word) for name in expected]
    assert tmdb.calls[-1] == ("search", (word, media_type))  # asked TMDB for that type


def test_the_local_fallback_honours_the_media_type(
    api: TestClient, tmdb: FakeProvider, word: str, db_session: Session
) -> None:
    add_candidate(db_session, f"{word} Local Film")
    add_candidate(db_session, f"{word} Local Show", media_type="tv")
    tmdb.search_failing = True

    body = api.get("/api/search", params={"q": word, "media_type": "tv"}).json()

    assert (body["source"], result_names(body)) == ("local", [f"{word} Local Show"])


def test_an_unknown_media_type_is_rejected(api: TestClient) -> None:
    assert api.get("/api/search", params={"q": "x", "media_type": "film"}).status_code == 422


@pytest.mark.parametrize("q", ["", "   ", "x" * 101])
def test_search_needs_a_query(api: TestClient, q: str) -> None:
    assert api.get("/api/search", params={"q": q}).status_code == 422


def test_search_needs_a_session(client: TestClient) -> None:
    assert client.get("/api/search", params={"q": "arrival"}).status_code == 401


# --- Favorites found through search ---------------------------------------------------------


def add_favorite(client: TestClient, title_id: int) -> list[str]:
    token = client.get("/api/auth/session").json()["csrf_token"]
    response = send(client, "POST", "/api/me/favorites", {"title_id": title_id}, csrf_token=token)
    assert response.status_code == 201, response.text
    return [f["name"] for f in response.json()["favorites"]]


def test_a_searched_title_can_be_a_favorite_and_gets_its_details(
    api: TestClient, word: str, db_session: Session
) -> None:
    [odyssey] = [r for r in search(api, word)["results"] if r["name"] == f"{word} Odyssey"]

    assert add_favorite(api, odyssey["id"]) == [f"{word} Odyssey"]

    db_session.expire_all()
    title = db_session.get(Title, odyssey["id"])
    assert title is not None and title.detail_level == "full"  # hydrated after the commit
    neighbors = db_session.scalars(
        select(ProviderTitleRecommendation).where(
            ProviderTitleRecommendation.source_title_id == odyssey["id"]
        )
    ).all()
    assert len(neighbors) == 1  # its TMDB list can now anchor "Because you picked"


def test_the_favorite_stands_even_if_fetching_details_fails(
    api: TestClient, tmdb: FakeProvider, word: str, db_session: Session
) -> None:
    [files] = [r for r in search(api, word)["results"] if r["name"] == f"The {word} Files"]
    tmdb.failing = {ref for ref in tmdb._details}  # every details call fails

    assert add_favorite(api, files["id"]) == [f"The {word} Files"]

    db_session.expire_all()
    title = db_session.get(Title, files["id"])
    assert title is not None
    assert (title.detail_level, title.last_sync_error is not None) == ("summary", True)
