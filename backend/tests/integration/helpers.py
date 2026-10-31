"""Small helpers for driving the auth API the way the SPA does."""

import itertools
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from screening_room.core.security import hash_session_token
from screening_room.modules.catalog import service as catalog
from screening_room.modules.catalog.models import Genre, IngestionRun
from screening_room.modules.catalog.providers.base import MediaType
from screening_room.modules.catalog.providers.fake import fake_title
from screening_room.modules.identity.models import UserSession
from tests.conftest import TEST_ORIGIN

PASSWORD = "correct horse battery"
SESSION_COOKIE = "sr_session"  # test settings: cookie_prefix_host=False


def expire_session(db_session: Session, client: TestClient) -> None:
    """Make the client's current session expire, as if 30 days had passed."""
    token_hash = hash_session_token(client.cookies[SESSION_COOKIE])
    db_session.execute(
        update(UserSession)
        .where(UserSession.token_hash == token_hash)  # only this test's session
        .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    )
    db_session.commit()  # only releases a savepoint; still undone after the test


def bootstrap_csrf(client: TestClient) -> str:
    """GET /api/auth/session, as the SPA does on startup: returns the CSRF token."""
    response = client.get("/api/auth/session")
    assert response.status_code == 200, response.text
    token: str = response.json()["csrf_token"]
    return token


def post(
    client: TestClient,
    path: str,
    json: object = None,
    *,
    csrf_token: str | None,
    origin: str | None = TEST_ORIGIN,
) -> Response:
    """POST with the headers a same-origin browser request would carry."""
    headers = {}
    if origin is not None:
        headers["Origin"] = origin
    if csrf_token is not None:
        headers["X-CSRF-Token"] = csrf_token
    return client.post(path, json=json, headers=headers)


def register(
    client: TestClient, email: str = "ada@example.com", password: str = PASSWORD
) -> Response:
    token = bootstrap_csrf(client)
    return post(
        client, "/api/auth/register", {"email": email, "password": password}, csrf_token=token
    )


def login(client: TestClient, email: str, password: str = PASSWORD) -> Response:
    token = bootstrap_csrf(client)
    return post(client, "/api/auth/login", {"email": email, "password": password}, csrf_token=token)


_candidate_ids = itertools.count(970_000_000)


def add_candidate(
    db_session: Session,
    name: str,
    *,
    media_type: MediaType = "movie",
    genre_ids: tuple[int, ...] = (18,),  # TMDB genre ids; 18 = Drama
    vote_count: int = 1000,
    original_name: str | None = None,
) -> int:
    """Put a fully hydrated candidate-pool title in the catalog; returns its id."""
    details = fake_title(
        media_type, next(_candidate_ids), name, genre_ids=genre_ids, vote_count=vote_count
    )
    details = replace(details, summary=replace(details.summary, original_name=original_name))
    now = datetime.now(UTC)
    run = IngestionRun(command="ingest", params={}, status="succeeded", counts={})
    db_session.add(run)
    db_session.flush()
    title_id = catalog.upsert_title_summary(db_session, details.summary, now)
    catalog.upsert_pool_membership(db_session, title_id, "test:source", 1, run.id)
    catalog.apply_title_details(
        db_session, title_id, details, catalog.load_genre_map(db_session, "tmdb"), run.id, now
    )
    db_session.commit()
    return title_id


def genre_id(db_session: Session, slug: str) -> int:
    return db_session.scalars(select(Genre.id).where(Genre.slug == slug)).one()


def send(
    client: TestClient, method: str, path: str, json: object = None, *, csrf_token: str
) -> Response:
    """A PUT/POST/DELETE with the headers a same-origin browser request carries."""
    headers = {"Origin": TEST_ORIGIN, "X-CSRF-Token": csrf_token}
    return client.request(method, path, json=json, headers=headers)
