"""Actions on a recommendation: the library change, its attribution and the event,
all in one commit (overview.md §6.4, data-model.md §3.4).

Starts from an EMPTY catalog (conftest.py), so the pool is exactly what's added here.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from screening_room.modules.discovery.models import RecRequest, RecResultEvent
from screening_room.modules.library.models import (
    Rating,
    TitleFeedback,
    ViewingEvent,
    WatchlistItem,
)
from tests.integration.helpers import add_candidate, register, send

Send = Callable[..., Response]
RELEASED = date(2016, 11, 10)


def signed_up(client: TestClient, email: str) -> Send:
    response = register(client, email=email)
    assert response.status_code == 201, response.text
    csrf_token = response.json()["csrf_token"]

    def call(method: str, path: str, json: object = None) -> Response:
        return send(client, method, path, json, csrf_token=csrf_token)

    return call


@pytest.fixture
def me(client: TestClient) -> Send:
    return signed_up(client, "events@example.com")


@pytest.fixture
def results(me: Send, db_session: Session, empty_catalog: None) -> dict[int, int]:
    """A shortlist for `me`: title id -> result id."""
    for name in ("Arrival", "Dune", "Contact", "Moon"):
        add_candidate(db_session, name, release_date=RELEASED)
    body = me("POST", "/api/recommendations", {"limit": 3}).json()
    return {r["title"]["id"]: r["result_id"] for r in body["results"]}


def event(me: Send, result_id: int, **body: object) -> Response:
    return me("POST", f"/api/recommendations/results/{result_id}/events", body)


def events_of(db_session: Session, result_id: int) -> list[str]:
    return list(
        db_session.scalars(
            select(RecResultEvent.event_type)
            .where(RecResultEvent.result_id == result_id)
            .order_by(RecResultEvent.id)
        )
    )


def first(results: dict[int, int]) -> tuple[int, int]:
    title_id = min(results)
    return title_id, results[title_id]


# --- Each action ----------------------------------------------------------------------------


def test_saving_adds_to_the_watchlist_with_attribution(
    me: Send, results: dict[int, int], db_session: Session
) -> None:
    title_id, result_id = first(results)

    response = event(me, result_id, type="saved")

    assert response.status_code == 201, response.text
    assert response.json()["in_watchlist"] is True
    item = db_session.get(WatchlistItem, (me_id(db_session, title_id), title_id))
    assert item is not None and item.rec_result_id == result_id
    assert events_of(db_session, result_id) == ["saved"]


def test_watching_with_a_date_records_an_attributed_viewing(
    me: Send, results: dict[int, int], db_session: Session
) -> None:
    title_id, result_id = first(results)

    state = event(me, result_id, type="watched", watched_on="2026-10-30").json()

    assert (state["watch_count"], state["last_watched_on"]) == (1, "2026-10-30")
    viewing = db_session.scalars(
        select(ViewingEvent).where(ViewingEvent.title_id == title_id)
    ).one()
    assert viewing.rec_result_id == result_id


def test_rating_records_the_rating_and_the_implied_viewing(
    me: Send, results: dict[int, int], db_session: Session
) -> None:
    title_id, result_id = first(results)

    state = event(me, result_id, type="rated", rating=4).json()

    assert (state["rating"], state["watch_count"]) == (4, 1)
    rating = db_session.scalars(select(Rating).where(Rating.title_id == title_id)).one()
    viewing = db_session.scalars(
        select(ViewingEvent).where(ViewingEvent.title_id == title_id)
    ).one()
    assert rating.rec_result_id == viewing.rec_result_id == result_id
    assert events_of(db_session, result_id) == ["rated"]


def test_not_for_me_is_recorded_and_attributed(
    me: Send, results: dict[int, int], db_session: Session
) -> None:
    title_id, result_id = first(results)

    assert event(me, result_id, type="not_for_me").json()["not_for_me"] is True
    feedback = db_session.scalars(select(TitleFeedback).where(TitleFeedback.title_id == title_id))
    assert feedback.one().rec_result_id == result_id


@pytest.mark.parametrize("kind", ["opened", "skipped"])
def test_opening_and_skipping_are_only_logged(
    me: Send, results: dict[int, int], db_session: Session, kind: str
) -> None:
    title_id, result_id = first(results)

    state = event(me, result_id, type=kind).json()
    event(me, result_id, type=kind)  # append-only: every time is a row

    assert state == {
        "title_id": title_id,
        "in_watchlist": False,
        "watch_count": 0,
        "last_watched_on": None,
        "rating": None,
        "not_for_me": False,
    }
    assert events_of(db_session, result_id) == [kind, kind]


# --- Validation and atomicity ---------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"type": "rated"},  # needs a rating
        {"type": "rated", "rating": 6},
        {"type": "saved", "rating": 4},  # a rating only goes with "rated"
        {"type": "saved", "watched_on": "2026-10-01"},
        {"type": "clicked"},
    ],
)
def test_invalid_events_are_rejected(
    me: Send, results: dict[int, int], db_session: Session, body: dict[str, object]
) -> None:
    _, result_id = first(results)

    response = me("POST", f"/api/recommendations/results/{result_id}/events", body)

    assert response.status_code == 422
    assert events_of(db_session, result_id) == []


def test_a_rejected_library_change_logs_no_event(
    me: Send, results: dict[int, int], db_session: Session
) -> None:
    _, result_id = first(results)
    next_week = (datetime.now(UTC).date() + timedelta(days=7)).isoformat()

    response = event(me, result_id, type="watched", watched_on=next_week)

    assert response.json()["error"]["code"] == "watched_on_in_future"
    assert events_of(db_session, result_id) == []


# --- Ownership ------------------------------------------------------------------------------


def test_another_users_result_is_not_found_and_untouched(
    client: TestClient, results: dict[int, int], db_session: Session
) -> None:
    title_id, result_id = first(results)
    other = signed_up(TestClient(client.app), "intruder@example.com")

    response = event(other, result_id, type="saved")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "result_not_found"
    assert events_of(db_session, result_id) == []
    assert (
        db_session.scalars(select(WatchlistItem).where(WatchlistItem.title_id == title_id)).all()
        == []
    )


def test_an_unknown_result_is_not_found(me: Send, results: dict[int, int]) -> None:
    assert event(me, 999_999_999_999, type="opened").status_code == 404


def test_writes_need_a_session_and_csrf(client: TestClient, results: dict[int, int]) -> None:
    _, result_id = first(results)
    path = f"/api/recommendations/results/{result_id}/events"

    assert send(client, "POST", path, {"type": "saved"}, csrf_token="wrong").status_code == 403
    anonymous = TestClient(client.app)  # a second browser, never signed in
    token = anonymous.get("/api/auth/session").json()["csrf_token"]
    assert send(anonymous, "POST", path, {"type": "saved"}, csrf_token=token).status_code == 401


# --- Attribution is optional ----------------------------------------------------------------


def test_deleting_the_logs_keeps_the_library_and_drops_the_attribution(
    me: Send, results: dict[int, int], db_session: Session
) -> None:
    title_id, result_id = first(results)
    event(me, result_id, type="saved")

    db_session.execute(delete(RecRequest))  # cascades to results and their events
    db_session.commit()

    item = db_session.get(WatchlistItem, (me_id(db_session, title_id), title_id))
    assert item is not None and item.rec_result_id is None  # SET NULL: never blocks deletion
    assert db_session.scalars(select(RecResultEvent)).all() == []


def me_id(db_session: Session, title_id: int) -> int:
    """The user who has this title in their library (each test has one)."""
    return db_session.scalars(
        select(WatchlistItem.user_id).where(WatchlistItem.title_id == title_id)
    ).one()
