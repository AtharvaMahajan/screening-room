"""Library endpoints: the user-title state rules (data-model.md §5) and their
authorization (security.md §6). Titles are created per test, so the real pool
in the dev database doesn't matter."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from screening_room.modules.library.models import ViewingEvent
from tests.integration.helpers import add_candidate, register, send

Send = Callable[..., Response]


def signed_up(client: TestClient, email: str) -> Send:
    response = register(client, email=email)
    assert response.status_code == 201, response.text
    csrf_token = response.json()["csrf_token"]

    def call(method: str, path: str, json: object = None) -> Response:
        return send(client, method, path, json, csrf_token=csrf_token)

    return call


@pytest.fixture
def me(client: TestClient) -> Send:
    return signed_up(client, "library@example.com")


@pytest.fixture
def title(db_session: Session) -> int:
    return add_candidate(db_session, "Arrival")


def state(me: Send, title_id: int) -> dict[str, object]:
    response = me("GET", f"/api/me/titles/{title_id}")
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


NOTHING = {
    "in_watchlist": False,
    "watch_count": 0,
    "last_watched_on": None,
    "rating": None,
    "not_for_me": False,
}


def test_an_untouched_title_has_no_state(me: Send, title: int) -> None:
    assert state(me, title) == {"title_id": title, **NOTHING}


# --- Watchlist ------------------------------------------------------------------------------


def test_saving_twice_keeps_one_entry_and_removing_is_idempotent(me: Send, title: int) -> None:
    first = me("PUT", f"/api/me/watchlist/{title}")
    second = me("PUT", f"/api/me/watchlist/{title}")

    assert first.status_code == second.status_code == 200
    assert second.json()["in_watchlist"] is True

    assert me("DELETE", f"/api/me/watchlist/{title}").json()["in_watchlist"] is False
    assert me("DELETE", f"/api/me/watchlist/{title}").status_code == 200


# --- Viewing history ------------------------------------------------------------------------


def test_watching_takes_a_title_off_the_watchlist(me: Send, title: int) -> None:
    me("PUT", f"/api/me/watchlist/{title}")

    response = me("POST", f"/api/me/history/{title}", {"watched_on": "2026-10-01"})

    assert response.status_code == 201, response.text
    assert response.json() | {"title_id": 0} == {
        **NOTHING,
        "title_id": 0,
        "watch_count": 1,
        "last_watched_on": "2026-10-01",
    }


def test_watching_again_records_a_rewatch(me: Send, title: int) -> None:
    me("POST", f"/api/me/history/{title}", {"watched_on": "2025-01-05"})
    me("POST", f"/api/me/history/{title}", {})  # no date: also fine

    after = state(me, title)

    assert (after["watch_count"], after["last_watched_on"]) == (2, "2025-01-05")


def test_a_watch_date_cannot_be_in_the_future(me: Send, title: int) -> None:
    next_week = (datetime.now(UTC).date() + timedelta(days=7)).isoformat()

    response = me("POST", f"/api/me/history/{title}", {"watched_on": next_week})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "watched_on_in_future"
    assert state(me, title)["watch_count"] == 0  # nothing half-saved


def test_unmarking_watched_removes_every_viewing_but_keeps_the_rating(me: Send, title: int) -> None:
    me("POST", f"/api/me/history/{title}", {})
    me("POST", f"/api/me/history/{title}", {})
    me("PUT", f"/api/me/ratings/{title}", {"value": 4})

    after = me("DELETE", f"/api/me/history/{title}").json()

    assert (after["watch_count"], after["rating"]) == (0, 4)


# --- Ratings --------------------------------------------------------------------------------


def test_rating_an_unwatched_title_marks_it_watched(me: Send, title: int) -> None:
    me("PUT", f"/api/me/watchlist/{title}")

    after = me("PUT", f"/api/me/ratings/{title}", {"value": 5}).json()

    assert (after["rating"], after["watch_count"], after["in_watchlist"]) == (5, 1, False)


def test_changing_a_rating_adds_no_viewing(me: Send, title: int, db_session: Session) -> None:
    me("PUT", f"/api/me/ratings/{title}", {"value": 2})

    after = me("PUT", f"/api/me/ratings/{title}", {"value": 3}).json()

    assert (after["rating"], after["watch_count"]) == (3, 1)


def test_removing_a_rating_keeps_the_viewings(me: Send, title: int) -> None:
    me("PUT", f"/api/me/ratings/{title}", {"value": 4})

    after = me("DELETE", f"/api/me/ratings/{title}").json()

    assert (after["rating"], after["watch_count"]) == (None, 1)


@pytest.mark.parametrize("value", [0, 6, 3.5, None])
def test_ratings_are_whole_stars_from_1_to_5(me: Send, title: int, value: object) -> None:
    response = me("PUT", f"/api/me/ratings/{title}", {"value": value})

    assert response.status_code == 422
    assert state(me, title)["rating"] is None


# --- Not for me -----------------------------------------------------------------------------


def test_not_for_me_can_be_undone_and_is_independent_of_a_rating(me: Send, title: int) -> None:
    me("PUT", f"/api/me/ratings/{title}", {"value": 2})

    marked = me("PUT", f"/api/me/not-for-me/{title}")
    again = me("PUT", f"/api/me/not-for-me/{title}")  # idempotent

    assert (marked.json()["not_for_me"], marked.json()["rating"]) == (True, 2)
    assert again.status_code == 200
    undone = me("DELETE", f"/api/me/not-for-me/{title}").json()
    assert (undone["not_for_me"], undone["rating"]) == (False, 2)


# --- Titles and authorization ---------------------------------------------------------------

ENDPOINTS = [
    ("GET", "/api/me/titles/{id}", None),
    ("PUT", "/api/me/watchlist/{id}", None),
    ("DELETE", "/api/me/watchlist/{id}", None),
    ("POST", "/api/me/history/{id}", {}),
    ("DELETE", "/api/me/history/{id}", None),
    ("PUT", "/api/me/ratings/{id}", {"value": 3}),
    ("DELETE", "/api/me/ratings/{id}", None),
    ("PUT", "/api/me/not-for-me/{id}", None),
    ("DELETE", "/api/me/not-for-me/{id}", None),
]


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_unknown_titles_are_404(me: Send, method: str, path: str, body: object) -> None:
    response = me(method, path.format(id=999_999_999_999), body)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "title_not_found"


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
def test_signed_out_users_get_401(
    client: TestClient, title: int, method: str, path: str, body: object
) -> None:
    token = client.get("/api/auth/session").json()["csrf_token"]

    response = send(client, method, path.format(id=title), body, csrf_token=token)

    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path", "body"), [e for e in ENDPOINTS if e[0] != "GET"])
def test_writes_need_the_csrf_token(
    client: TestClient, me: Send, title: int, method: str, path: str, body: object
) -> None:
    response = send(client, method, path.format(id=title), body, csrf_token="wrong")

    assert response.status_code == 403
    assert state(me, title) == {"title_id": title, **NOTHING}


def test_each_user_sees_and_changes_only_their_own_library(
    client: TestClient, me: Send, title: int, db_session: Session
) -> None:
    me("PUT", f"/api/me/ratings/{title}", {"value": 5})
    me("PUT", f"/api/me/not-for-me/{title}")
    me("PUT", f"/api/me/watchlist/{title}")  # last: rating takes a title off the watchlist
    mine = state(me, title)
    assert mine == {**mine, "in_watchlist": True, "watch_count": 1, "rating": 5, "not_for_me": True}
    other = signed_up(TestClient(client.app), "other@example.com")

    # The other user sees nothing of mine...
    assert state(other, title) == {"title_id": title, **NOTHING}
    # ...and removing "their" entries doesn't touch mine.
    for method, path, body in ENDPOINTS:
        if method == "DELETE":
            assert other(method, path.format(id=title), body).status_code == 200
    assert state(me, title) == mine
    # Their own actions are theirs alone.
    other("POST", f"/api/me/history/{title}", {"watched_on": str(date(2020, 1, 1))})
    assert state(me, title)["last_watched_on"] is None
    viewers = db_session.scalar(
        select(func.count(func.distinct(ViewingEvent.user_id))).where(
            ViewingEvent.title_id == title
        )
    )
    assert viewers == 2
