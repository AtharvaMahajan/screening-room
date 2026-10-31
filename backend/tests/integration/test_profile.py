"""Taste profile endpoints: genre preferences and favorites (data-model.md §3.3, FR-02)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from screening_room.modules.identity.models import User
from screening_room.modules.profile import service
from screening_room.modules.profile.schemas import MAX_FAVORITES
from tests.integration.helpers import add_candidate, genre_id, register, send

Send = Callable[..., Response]


@pytest.fixture
def me(client: TestClient) -> Send:
    """Sign up, then return a function that sends CSRF-protected requests as that user."""
    response = register(client, email="profile@example.com")
    assert response.status_code == 201, response.text
    csrf_token = response.json()["csrf_token"]

    def call(method: str, path: str, json: object = None) -> Response:
        return send(client, method, path, json, csrf_token=csrf_token)

    return call


def favorite_names(response: Response) -> list[str]:
    return [card["name"] for card in response.json()["favorites"]]


# --- Genre preferences ----------------------------------------------------------------------


def test_a_new_user_has_no_preferences(me: Send) -> None:
    assert me("GET", "/api/me/preferences").json() == {
        "liked_genre_ids": [],
        "avoided_genre_ids": [],
    }


def test_preferences_are_replaced_wholesale(me: Send, db_session: Session) -> None:
    drama, comedy, horror = (genre_id(db_session, s) for s in ("drama", "comedy", "horror"))

    first = me(
        "PUT",
        "/api/me/preferences",
        {"liked_genre_ids": [drama, comedy], "avoided_genre_ids": [horror]},
    )
    second = me(
        "PUT", "/api/me/preferences", {"liked_genre_ids": [comedy], "avoided_genre_ids": []}
    )

    assert first.status_code == 200, first.text
    assert second.json() == {"liked_genre_ids": [comedy], "avoided_genre_ids": []}
    assert me("GET", "/api/me/preferences").json() == second.json()  # it was saved


def test_a_genre_cannot_be_both_liked_and_avoided(me: Send, db_session: Session) -> None:
    drama = genre_id(db_session, "drama")

    response = me(
        "PUT", "/api/me/preferences", {"liked_genre_ids": [drama], "avoided_genre_ids": [drama]}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "genre_conflict"


@pytest.mark.parametrize("slug", ["news", "talk", "tv-movie"])
def test_genres_the_pool_skips_cannot_be_chosen(me: Send, db_session: Session, slug: str) -> None:
    response = me("PUT", "/api/me/preferences", {"liked_genre_ids": [genre_id(db_session, slug)]})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_genre"


def test_unknown_genre_ids_are_rejected(me: Send) -> None:
    response = me("PUT", "/api/me/preferences", {"avoided_genre_ids": [999_999]})

    assert response.json()["error"]["code"] == "unknown_genre"


# --- Favorites ------------------------------------------------------------------------------


def test_add_list_and_remove_favorites(me: Send, db_session: Session) -> None:
    arrival = add_candidate(db_session, "Profile Arrival")
    dune = add_candidate(db_session, "Profile Dune")

    added = me("POST", "/api/me/favorites", {"title_id": arrival})
    me("POST", "/api/me/favorites", {"title_id": dune})
    removed = me("DELETE", f"/api/me/favorites/{arrival}")

    assert added.status_code == 201
    assert favorite_names(added) == ["Profile Arrival"]
    assert added.json()["favorites"][0] == {
        "id": arrival,
        "media_type": "movie",
        "name": "Profile Arrival",
        "year": None,
        "poster_url": None,
    }
    assert favorite_names(removed) == ["Profile Dune"]
    assert favorite_names(me("GET", "/api/me/favorites")) == ["Profile Dune"]


def test_favorites_keep_the_order_they_were_picked(me: Send, db_session: Session) -> None:
    ids = [add_candidate(db_session, f"Order {n}") for n in (3, 1, 2)]

    for title_id in ids:
        me("POST", "/api/me/favorites", {"title_id": title_id})

    assert favorite_names(me("GET", "/api/me/favorites")) == ["Order 3", "Order 1", "Order 2"]


def test_adding_and_removing_are_idempotent(me: Send, db_session: Session) -> None:
    title_id = add_candidate(db_session, "Twice")

    first = me("POST", "/api/me/favorites", {"title_id": title_id})
    again = me("POST", "/api/me/favorites", {"title_id": title_id})
    me("DELETE", f"/api/me/favorites/{title_id}")
    removed_again = me("DELETE", f"/api/me/favorites/{title_id}")

    assert (first.status_code, again.status_code) == (201, 200)
    assert favorite_names(again) == ["Twice"]  # still one entry
    assert removed_again.status_code == 200
    assert favorite_names(removed_again) == []


def test_at_most_ten_favorites(me: Send, db_session: Session) -> None:
    for n in range(MAX_FAVORITES):
        assert (
            me(
                "POST", "/api/me/favorites", {"title_id": add_candidate(db_session, f"Fav {n}")}
            ).status_code
            == 201
        )

    eleventh = me(
        "POST", "/api/me/favorites", {"title_id": add_candidate(db_session, "One too many")}
    )

    assert eleventh.status_code == 409
    assert eleventh.json()["error"]["code"] == "favorites_limit"
    assert me("GET", "/api/me/favorites").json()["max_favorites"] == MAX_FAVORITES


def test_only_pool_titles_can_be_favorites(me: Send) -> None:
    response = me("POST", "/api/me/favorites", {"title_id": 2**62})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "title_not_found"


# --- Privacy and protection ------------------------------------------------------------------


def test_each_user_sees_only_their_own_profile(
    me: Send, client: TestClient, db_session: Session
) -> None:
    title_id = add_candidate(db_session, "Mine")
    me("POST", "/api/me/favorites", {"title_id": title_id})
    me("PUT", "/api/me/preferences", {"liked_genre_ids": [genre_id(db_session, "drama")]})

    client.cookies.clear()  # someone else signs up in the same browser
    register(client, email="someone-else@example.com")

    assert client.get("/api/me/favorites").json()["favorites"] == []
    assert client.get("/api/me/preferences").json()["liked_genre_ids"] == []


def test_profile_writes_need_a_csrf_token(
    me: Send, client: TestClient, db_session: Session
) -> None:
    response = client.put(
        "/api/me/preferences",
        json={"liked_genre_ids": []},
        headers={"Origin": "http://testserver"},  # right origin, no token
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"


def test_profile_needs_sign_in(client: TestClient) -> None:
    assert client.get("/api/me/preferences").status_code == 401
    assert client.get("/api/me/favorites").status_code == 401


def test_taste_signals_for_the_recommender(me: Send, db_session: Session) -> None:
    drama, horror = genre_id(db_session, "drama"), genre_id(db_session, "horror")
    title_id = add_candidate(db_session, "Signal")
    me("PUT", "/api/me/preferences", {"liked_genre_ids": [drama], "avoided_genre_ids": [horror]})
    me("POST", "/api/me/favorites", {"title_id": title_id})
    user_id = db_session.scalars(select(User.id).where(User.email == "profile@example.com")).one()

    signals = service.taste_signals(db_session, user_id)

    assert signals.liked_genre_ids == frozenset({drama})
    assert signals.avoided_genre_ids == frozenset({horror})
    assert signals.favorite_title_ids == (title_id,)
