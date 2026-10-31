"""GET /api/titles/{id}: local first, read-through when stale (catalog-ingestion.md §11-12).

TMDB is replaced by a FakeProvider through FastAPI's dependency override. Titles
are created per test with unique provider ids, so the real pool doesn't matter.
"""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from screening_room.modules.catalog import service
from screening_room.modules.catalog.dependencies import get_catalog_provider
from screening_room.modules.catalog.models import Title
from screening_room.modules.catalog.providers.base import (
    Credit,
    ProviderRef,
    TitleDetails,
)
from screening_room.modules.catalog.providers.fake import FakeProvider, fake_title
from tests.integration.helpers import register

NOW = datetime.now(UTC)
FRESH = NOW - timedelta(days=1)
STALE = NOW - timedelta(days=30)  # older than the 14-day TTL
_ids = count(950_000_000)


class WatchedProvider(FakeProvider):
    """A FakeProvider that fails the test if TMDB is called inside a transaction."""

    def __init__(self, titles: list[TitleDetails], session: Session) -> None:
        super().__init__(titles)
        self._session = session

    def get_details(self, ref: ProviderRef) -> TitleDetails:
        assert not self._session.in_transaction(), "TMDB called with a transaction open"
        return super().get_details(ref)


def movie(name: str = "Arrival") -> TitleDetails:
    details = fake_title("movie", next(_ids), name, genre_ids=(18, 878))
    return replace(
        details,
        summary=replace(details.summary, poster_path="/poster.jpg"),
        credits=(
            Credit(1, "Amy Adams", "/amy.jpg", "cast", "Louise Banks", 0),
            Credit(2, "Jeremy Renner", None, "cast", "Ian Donnelly", 1),
            Credit(3, "Denis Villeneuve", None, "director", None, 0),
        ),
    )


def store(db_session: Session, details: TitleDetails, synced_at: datetime | None) -> int:
    """Put a title in the catalog: hydrated at `synced_at`, or summary-only if None."""
    title_id = service.upsert_title_summary(db_session, details.summary, NOW)
    if synced_at is not None:
        genre_map = service.load_genre_map(db_session, "tmdb")
        service.apply_title_details(db_session, title_id, details, genre_map, None, synced_at)
    db_session.commit()
    return title_id


@pytest.fixture
def signed_in(client: TestClient) -> TestClient:
    assert register(client, email="viewer@example.com").status_code == 201
    return client


def use_provider(client: TestClient, provider: FakeProvider | None) -> None:
    app = client.app
    assert isinstance(app, FastAPI)
    app.dependency_overrides[get_catalog_provider] = lambda: provider


@pytest.fixture
def api(signed_in: TestClient) -> TestClient:
    """A signed-in client; tests choose the provider with use_provider()."""
    return signed_in


def get(client: TestClient, title_id: int) -> dict[str, Any]:
    response = client.get(f"/api/titles/{title_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


# --- Served locally -----------------------------------------------------------------------


def test_a_fresh_title_is_served_without_calling_tmdb(api: TestClient, db_session: Session) -> None:
    details = movie()
    title_id = store(db_session, details, FRESH)
    provider = WatchedProvider([details], db_session)
    use_provider(api, provider)

    body = get(api, title_id)

    assert body["metadata_status"] == "fresh"
    assert provider.calls == []


def test_the_response_has_everything_the_page_needs(api: TestClient, db_session: Session) -> None:
    title_id = store(db_session, movie(), FRESH)
    use_provider(api, None)

    body = get(api, title_id)

    assert body["name"] == "Arrival"
    assert body["media_type"] == "movie"
    assert body["runtime_minutes"] == 100
    # Image paths are stored; URLs are built from configuration (ADR-0004).
    assert body["poster_url"] == "https://image.tmdb.org/t/p/w342/poster.jpg"
    assert [g["slug"] for g in body["genres"]] == ["drama", "science-fiction"]
    assert body["cast"] == [
        {
            "name": "Amy Adams",
            "character": "Louise Banks",
            "profile_url": "https://image.tmdb.org/t/p/w185/amy.jpg",
        },
        {"name": "Jeremy Renner", "character": "Ian Donnelly", "profile_url": None},
    ]
    assert body["directors"] == ["Denis Villeneuve"]
    assert body["creators"] == []


# --- Read-through ----------------------------------------------------------------------------


def test_a_stale_title_is_refreshed_outside_any_transaction(
    api: TestClient, db_session: Session
) -> None:
    old = movie("Old name")
    title_id = store(db_session, old, STALE)
    new = replace(old, summary=replace(old.summary, name="New name"))
    provider = WatchedProvider([new], db_session)  # asserts no open transaction
    use_provider(api, provider)

    body = get(api, title_id)

    assert body["metadata_status"] == "fresh"
    assert body["name"] == "New name"
    assert provider.calls == [("get_details", old.summary.ref)]
    synced = db_session.scalar(select(Title.details_synced_at).where(Title.id == title_id))
    assert synced is not None and synced > STALE  # the refresh was committed


def test_a_summary_only_title_is_hydrated_on_first_view(
    api: TestClient, db_session: Session
) -> None:
    details = movie()
    title_id = store(db_session, details, synced_at=None)
    use_provider(api, WatchedProvider([details], db_session))

    body = get(api, title_id)

    assert body["metadata_status"] == "fresh"
    assert body["directors"] == ["Denis Villeneuve"]


@pytest.mark.parametrize(
    ("synced_at", "expected"),
    [(STALE, "stale"), (None, "partial")],  # full-but-old vs summary-only
)
def test_tmdb_down_still_serves_the_page(
    api: TestClient, db_session: Session, synced_at: datetime | None, expected: str
) -> None:
    details = movie()
    title_id = store(db_session, details, synced_at)
    provider = WatchedProvider([details], db_session)
    provider.failing.add(details.summary.ref)
    use_provider(api, provider)

    body = get(api, title_id)

    assert body["metadata_status"] == expected
    assert body["name"] == "Arrival"
    errors = db_session.scalar(select(Title.sync_error_count).where(Title.id == title_id))
    assert errors == 1  # recorded for ingestion's report


def test_a_title_tmdb_no_longer_has_is_marked_missing(api: TestClient, db_session: Session) -> None:
    details = movie()
    title_id = store(db_session, details, STALE)
    provider = WatchedProvider([details], db_session)
    provider.missing.add(details.summary.ref)
    use_provider(api, provider)

    body = get(api, title_id)

    assert body["metadata_status"] == "stale"
    status = db_session.scalar(select(Title.provider_status).where(Title.id == title_id))
    assert status == "missing"


def test_without_a_tmdb_token_pages_show_what_we_have(api: TestClient, db_session: Session) -> None:
    title_id = store(db_session, movie(), STALE)
    use_provider(api, None)  # no TMDB_API_TOKEN configured

    assert get(api, title_id)["metadata_status"] == "stale"


def test_an_unmapped_genre_from_tmdb_does_not_break_the_page(
    api: TestClient, db_session: Session
) -> None:
    details = movie()
    title_id = store(db_session, details, STALE)
    weird = replace(details, summary=replace(details.summary, provider_genre_ids=(99999,)))
    use_provider(api, WatchedProvider([weird], db_session))

    body = get(api, title_id)

    assert body["metadata_status"] == "stale"
    assert [g["slug"] for g in body["genres"]] == ["drama", "science-fiction"]


# --- Errors and access -------------------------------------------------------------------------


def test_unknown_and_adult_titles_are_not_found(api: TestClient, db_session: Session) -> None:
    adult = movie("Adult")
    adult = replace(adult, summary=replace(adult.summary, adult=True))
    adult_id = store(db_session, adult, FRESH)
    use_provider(api, None)

    for title_id in (adult_id, 2**62):
        response = api.get(f"/api/titles/{title_id}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "title_not_found"


@pytest.mark.parametrize("bad_id", ["0", "-5", str(2**63), "abc"])
def test_invalid_ids_are_rejected(api: TestClient, bad_id: str) -> None:
    response = api.get(f"/api/titles/{bad_id}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_titles_require_sign_in(client: TestClient, db_session: Session) -> None:
    title_id = store(db_session, movie(), FRESH)

    response = client.get(f"/api/titles/{title_id}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"
