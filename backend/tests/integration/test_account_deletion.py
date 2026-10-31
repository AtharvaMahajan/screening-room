"""Account deletion: DELETE /api/me (security.md §6, data-model.md §6).

The cascade check is generic: every table with a user_id column must be empty
for the deleted user, so a table added later without ON DELETE CASCADE fails here.
"""

from collections.abc import Callable
from datetime import date

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from screening_room.db import Base
from screening_room.modules.catalog.models import Title
from screening_room.modules.discovery.models import RecResult, RecResultEvent
from screening_room.modules.identity.models import User
from tests.integration.helpers import (
    PASSWORD,
    SESSION_COOKIE,
    add_candidate,
    genre_id,
    login,
    register,
    send,
)

Send = Callable[..., Response]
RELEASED = date(2016, 11, 10)


def signed_up(client: TestClient, email: str) -> Send:
    response = register(client, email=email)
    assert response.status_code == 201, response.text

    def call(method: str, path: str, json: object = None) -> Response:
        # Always the current token: it rotates when the session changes.
        token = client.get("/api/auth/session").json()["csrf_token"]
        return send(client, method, path, json, csrf_token=token)

    return call


def user_id(db_session: Session, email: str) -> int:
    return db_session.scalars(select(User.id).where(User.email == email)).one()


def fill_account(me: Send, db_session: Session) -> tuple[int, int]:
    """Every kind of personal data: preferences, favorite, logs, events, library."""
    loved = add_candidate(db_session, "Loved", release_date=RELEASED)
    for name in ("Other A", "Other B", "Other C"):
        add_candidate(db_session, name, release_date=RELEASED)
    drama = genre_id(db_session, "drama")
    assert me("PUT", "/api/me/preferences", {"liked_genre_ids": [drama]}).status_code == 200
    assert me("POST", "/api/me/favorites", {"title_id": loved}).status_code == 201
    shortlist = me("POST", "/api/recommendations", {"limit": 3}).json()
    result = shortlist["results"][0]
    path = f"/api/recommendations/results/{result['result_id']}/events"
    assert me("POST", path, {"type": "saved"}).status_code == 201
    assert me("PUT", f"/api/me/ratings/{loved}", {"value": 5}).status_code == 200
    assert me("PUT", f"/api/me/not-for-me/{result['title']['id']}").status_code == 200
    return loved, result["result_id"]


def rows_for_user(db_session: Session, uid: int) -> dict[str, int]:
    """Row counts per table that has a user_id column (users itself by id)."""
    counts = {"users": db_session.scalar(select(func.count()).where(User.id == uid)) or 0}
    for table in Base.metadata.sorted_tables:
        if "user_id" in table.c:
            count = select(func.count()).select_from(table).where(table.c.user_id == uid)
            counts[table.name] = db_session.scalar(count) or 0
    return counts


def test_deleting_an_account_removes_all_personal_data_and_signs_out(
    client: TestClient, db_session: Session, empty_catalog: None
) -> None:
    me = signed_up(client, "leaving@example.com")
    loved, result_id = fill_account(me, db_session)
    uid = user_id(db_session, "leaving@example.com")
    before = rows_for_user(db_session, uid)
    assert all(before.values()), before  # the account really had data in every table

    response = me("DELETE", "/api/me", {"password": PASSWORD})

    assert response.status_code == 200, response.text
    assert response.json()["user"] is None
    assert SESSION_COOKIE not in client.cookies  # signed out in this browser
    db_session.expire_all()
    assert rows_for_user(db_session, uid) == dict.fromkeys(before, 0)
    # Rows that reference the user only indirectly are gone too...
    assert db_session.get(RecResult, result_id) is None
    events = select(func.count()).where(RecResultEvent.result_id == result_id)
    assert db_session.scalar(events) == 0
    # ...while the catalog is untouched.
    assert db_session.get(Title, loved) is not None


def test_a_deleted_account_cannot_sign_in_and_the_email_is_free_again(
    client: TestClient, db_session: Session
) -> None:
    me = signed_up(client, "again@example.com")
    assert me("DELETE", "/api/me", {"password": PASSWORD}).status_code == 200

    assert login(client, "again@example.com").status_code == 401
    assert register(client, email="again@example.com").status_code == 201


def test_the_wrong_password_deletes_nothing(client: TestClient, db_session: Session) -> None:
    me = signed_up(client, "careful@example.com")
    uid = user_id(db_session, "careful@example.com")

    response = me("DELETE", "/api/me", {"password": "not my password"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "wrong_password"
    assert rows_for_user(db_session, uid)["users"] == 1
    assert me("GET", "/api/me/favorites").status_code == 200  # still signed in


def test_other_accounts_are_untouched(client: TestClient, db_session: Session) -> None:
    other_client = TestClient(client.app)
    other = signed_up(other_client, "stays@example.com")
    assert other("PUT", "/api/me/preferences", {"liked_genre_ids": []}).status_code == 200
    me = signed_up(client, "goes@example.com")

    assert me("DELETE", "/api/me", {"password": PASSWORD}).status_code == 200

    assert other("GET", "/api/me/favorites").status_code == 200
    assert rows_for_user(db_session, user_id(db_session, "stays@example.com"))["users"] == 1


@pytest.mark.parametrize("token", [None, "wrong"])
def test_deletion_needs_the_csrf_token(
    client: TestClient, db_session: Session, token: str | None
) -> None:
    signed_up(client, "csrf@example.com")
    headers = {"Origin": "http://testserver"} | ({"X-CSRF-Token": token} if token else {})

    response = client.request("DELETE", "/api/me", json={"password": PASSWORD}, headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] in {"csrf_failed", "origin_rejected"}
    assert rows_for_user(db_session, user_id(db_session, "csrf@example.com"))["users"] == 1


def test_deletion_needs_a_session(client: TestClient) -> None:
    token = client.get("/api/auth/session").json()["csrf_token"]

    response = send(client, "DELETE", "/api/me", {"password": PASSWORD}, csrf_token=token)

    assert response.status_code == 401
