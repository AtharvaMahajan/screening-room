"""POST /api/recommendations against PostgreSQL (recommendation-engine.md §14-15).

Starts from an EMPTY catalog (conftest.py), so the pool is exactly what each test adds.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from screening_room.core.errors import AppError
from screening_room.modules.catalog import service as catalog
from screening_room.modules.catalog.models import ProviderTitleRecommendation, Title
from screening_room.modules.discovery.engine.config import ENGINE_VERSION
from screening_room.modules.discovery.models import RecRequest, RecResult
from screening_room.modules.discovery.service import CONFIG_HASH
from tests.integration.helpers import add_candidate, genre_id, post, register, send

Send = Callable[..., Response]
RELEASED = date(2016, 11, 10)  # the recommender skips unreleased titles


@pytest.fixture
def me(client: TestClient) -> Send:
    """Sign up, then return a function that sends CSRF-protected requests as that user."""
    response = register(client, email="recs@example.com")
    assert response.status_code == 201, response.text
    csrf_token = response.json()["csrf_token"]

    def call(method: str, path: str, json: object = None) -> Response:
        return send(client, method, path, json, csrf_token=csrf_token)

    return call


@dataclass(frozen=True)
class Pool:
    arrival: int  # the favorite
    dune: int  # Arrival's TMDB recommendation
    long_epic: int  # 200-minute movie
    shows: tuple[int, ...]
    others: tuple[int, ...]


@pytest.fixture
def pool(db_session: Session, empty_catalog: None) -> Pool:
    def movie(name: str, genres: tuple[int, ...], runtime_minutes: int | None = None) -> int:
        return add_candidate(
            db_session,
            name,
            genre_ids=genres,
            release_date=RELEASED,
            runtime_minutes=runtime_minutes,
        )

    def show(name: str, genres: tuple[int, ...]) -> int:
        return add_candidate(
            db_session, name, media_type="tv", genre_ids=genres, release_date=RELEASED
        )

    # TMDB genre ids: 18 Drama, 878 Science Fiction, 12 Adventure, 35 Comedy, 28 Action.
    pool = Pool(
        arrival=movie("Arrival", (18, 878)),
        dune=movie("Dune", (878, 12)),
        long_epic=movie("Long Epic", (12, 18), runtime_minutes=200),
        shows=(show("Show One", (18,)), show("Show Two", (35,))),
        others=(
            movie("Comedy One", (35,)),
            movie("Action One", (28,)),
            movie("Drama One", (18,)),
            movie("Comedy Two", (35, 18)),
        ),
    )
    arrival_provider_id, dune_provider_id = (
        db_session.scalars(select(Title.provider_id).where(Title.id == title_id)).one()
        for title_id in (pool.arrival, pool.dune)
    )
    db_session.add(
        ProviderTitleRecommendation(
            source_title_id=pool.arrival,
            provider="tmdb",
            target_media_type="movie",
            target_provider_id=dune_provider_id,
            provider_rank=1,
            fetched_at=datetime.now(UTC),
        )
    )
    assert arrival_provider_id  # the favorite is a real pool title too
    db_session.commit()
    return pool


def recommendations(me: Send, **body: object) -> Response:
    return me("POST", "/api/recommendations", body)


def result_ids(response: Response) -> list[int]:
    return [r["title"]["id"] for r in response.json()["results"]]


# --- The shortlist ----------------------------------------------------------------------------


def test_a_favorite_leads_to_an_explained_shortlist(
    me: Send, pool: Pool, db_session: Session
) -> None:
    assert me("POST", "/api/me/favorites", {"title_id": pool.arrival}).status_code == 201

    response = recommendations(me)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["cold_start"] is False
    assert 3 <= len(body["results"]) <= 5
    assert [r["rank"] for r in body["results"]] == list(range(1, len(body["results"]) + 1))
    assert pool.arrival not in result_ids(response)  # favorites aren't recommended back
    # Dune is Arrival's TMDB recommendation, so it comes with the favorite link.
    [dune] = [r for r in body["results"] if r["title"]["id"] == pool.dune]
    assert dune["reasons"][0] == {
        "type": "favorite_neighbor",
        "text": "Because you picked Arrival",
        "anchor_title_id": pool.arrival,
    }
    assert dune["title"] | {"poster_url": None} == {
        "id": pool.dune,
        "media_type": "movie",
        "name": "Dune",
        "year": 2016,
        "poster_url": None,
        "overview": None,
        "runtime_minutes": 100,
    }
    assert all(1 <= len(r["reasons"]) <= 2 for r in body["results"])


def test_the_request_and_its_results_are_logged(me: Send, pool: Pool, db_session: Session) -> None:
    me("POST", "/api/me/favorites", {"title_id": pool.arrival})

    body = recommendations(
        me, media_type="movie", max_runtime_minutes=150, exclude_title_ids=[pool.others[0]]
    ).json()

    request = db_session.get(RecRequest, body["request_id"])
    assert request is not None
    assert request.context == {
        "media_type": "movie",
        "genre_ids": [],
        "max_runtime_minutes": 150,
        "excluded_count": 1,
        "limit": 5,
    }
    assert (request.engine_version, request.config_hash) == (ENGINE_VERSION, CONFIG_HASH)
    assert (request.pool_size, request.candidate_count) == (9, 9)
    assert (request.anchor_count, request.anchors_without_neighbors) == (1, 0)
    assert request.cold_start is False
    assert request.latency_ms >= 0

    rows = db_session.scalars(
        select(RecResult).where(RecResult.request_id == request.id).order_by(RecResult.rank)
    ).all()
    assert [row.id for row in rows] == [r["result_id"] for r in body["results"]]
    assert [row.title_id for row in rows] == result_ids_of(body)
    # The stored reasons are exactly what the user was shown.
    assert [row.reasons for row in rows] == [r["reasons"] for r in body["results"]]
    dune = next(row for row in rows if row.title_id == pool.dune)
    assert dune.score_breakdown["favorite_neighbor"]["weighted"] > 0
    assert dune.score_breakdown["neighbor_source"]["anchor_title_id"] == pool.arrival


def result_ids_of(body: dict[str, list[dict[str, dict[str, int]]]]) -> list[int]:
    return [r["title"]["id"] for r in body["results"]]


def test_a_new_user_gets_a_cold_start_shortlist(me: Send, pool: Pool, db_session: Session) -> None:
    body = recommendations(me).json()

    assert body["cold_start"] is True
    assert [n["code"] for n in body["notices"]] == ["cold_start"]
    assert len(body["results"]) == 5


def test_context_filters_are_applied(me: Send, pool: Pool, db_session: Session) -> None:
    tv = recommendations(me, media_type="tv", limit=3).json()
    short_movies = recommendations(me, media_type="movie", max_runtime_minutes=120).json()
    comedies = recommendations(me, genre_ids=[genre_id(db_session, "comedy")], limit=3).json()

    assert set(result_ids_of(tv)) == set(pool.shows)  # only 2 shows exist...
    assert "few_results" in [n["code"] for n in tv["notices"]]  # ...so it says so, no padding
    assert pool.long_epic not in result_ids_of(short_movies)
    assert all(r["title"]["media_type"] == "movie" for r in short_movies["results"])
    assert all(
        any(reason["type"] == "runtime_fit" for reason in r["reasons"])
        for r in short_movies["results"]
    )
    # A genre pick is a filter: exactly the three comedies, each saying why.
    assert {r["title"]["name"] for r in comedies["results"]} == {
        "Comedy One",
        "Comedy Two",
        "Show Two",
    }
    assert all(r["reasons"][0]["type"] == "context_genre" for r in comedies["results"])


def test_excluded_titles_are_not_shown_again(me: Send, pool: Pool) -> None:
    """ "Show me more": send what was already shown, get the next ones."""
    first = result_ids(recommendations(me, limit=3))

    more = result_ids(recommendations(me, limit=3, exclude_title_ids=first))

    assert len(more) == 3
    assert not set(first) & set(more)


def test_a_rating_and_a_not_for_me_change_the_next_shortlist(me: Send, pool: Pool) -> None:
    """Roadmap M4 "done when": library feedback measurably changes recommendations."""
    before = recommendations(me).json()
    dismissed = next(
        r["title"]["id"]
        for r in before["results"]
        if r["title"]["id"] not in (pool.arrival, pool.dune)
    )

    assert me("PUT", f"/api/me/ratings/{pool.arrival}", {"value": 5}).status_code == 200
    assert me("PUT", f"/api/me/not-for-me/{dismissed}").status_code == 200
    after = recommendations(me).json()

    shown = result_ids_of(after)
    assert before["cold_start"] is True and after["cold_start"] is False
    assert dismissed not in shown  # not for me: never again (until undone)
    assert pool.arrival not in shown  # rated means watched
    # Arrival's TMDB recommendation now comes with the rating as its reason.
    [dune] = [r for r in after["results"] if r["title"]["id"] == pool.dune]
    assert dune["reasons"][0] == {
        "type": "favorite_neighbor",
        "text": "Because you rated Arrival 5★",
        "anchor_title_id": pool.arrival,
    }
    assert shown != result_ids_of(before)


# --- Validation -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"limit": 2},
        {"limit": 6},
        {"media_type": "documentary"},
        {"genre_ids": [1, 2, 3, 4]},
        {"max_runtime_minutes": 0},
        {"exclude_title_ids": list(range(1, 102))},
        {"exclude_title_ids": [0]},
    ],
)
def test_invalid_requests_are_rejected(me: Send, body: dict[str, object]) -> None:
    response = me("POST", "/api/recommendations", body)

    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"


@pytest.mark.parametrize("slug", ["news", "talk"])
def test_genres_the_pool_skips_cannot_be_asked_for(
    me: Send, db_session: Session, slug: str
) -> None:
    response = recommendations(me, genre_ids=[genre_id(db_session, slug)])

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_genre"


def test_signed_out_users_get_401(client: TestClient) -> None:
    token = client.get("/api/auth/session").json()["csrf_token"]

    response = post(client, "/api/recommendations", {}, csrf_token=token)

    assert response.status_code == 401


def test_a_missing_csrf_token_is_rejected(client: TestClient, me: Send) -> None:
    response = post(client, "/api/recommendations", {}, csrf_token=None)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


# --- One commit -------------------------------------------------------------------------------


def test_nothing_is_logged_if_the_request_fails_after_persisting(
    me: Send, pool: Pool, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The request and results are flushed, then something fails: nothing stays."""

    def fail(*args: object, **kwargs: object) -> None:
        raise AppError(500, "boom", "Simulated failure after the log rows were flushed.")

    monkeypatch.setattr(catalog, "title_previews", fail)

    response = recommendations(me)
    db_session.rollback()  # production closes the request's session, which rolls back

    assert response.status_code == 500
    assert db_session.scalar(select(func.count()).select_from(RecRequest)) == 0
