"""Login and registration rate limits through the real endpoints (security.md §8).

Limits are set low here; every test gets a fresh app, so a fresh limiter.
TestClient requests all come from the same client address.
"""

import pytest
from fastapi.testclient import TestClient

from screening_room.config import Settings
from tests.integration.helpers import PASSWORD, login, register


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "login_attempts_per_ip": 5,
            "login_failures_per_email": 3,
            "registrations_per_ip": 2,
        }
    )


def test_failed_logins_for_one_email_are_limited(client: TestClient) -> None:
    assert register(client, email="target@example.com").status_code == 201
    for _ in range(3):
        assert login(client, "target@example.com", "wrong password").status_code == 401

    blocked = login(client, "target@example.com")  # even the right password, for now

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert 0 < int(blocked.headers["Retry-After"]) <= 15 * 60
    # The limit is per address: another account is unaffected.
    assert register(client, email="other@example.com").status_code == 201
    assert login(client, "other@example.com").status_code == 200


def test_successful_logins_do_not_count_against_the_email(client: TestClient) -> None:
    assert register(client, email="regular@example.com").status_code == 201

    # 4 good logins: over the 3-failure limit, under the 5-per-IP limit.
    for _ in range(4):
        assert login(client, "regular@example.com").status_code == 200


def test_all_login_attempts_from_one_ip_are_limited(client: TestClient) -> None:
    for i in range(5):
        assert login(client, f"guess{i}@example.com", "x").status_code == 401

    blocked = login(client, "anyone@example.com", PASSWORD)

    assert blocked.status_code == 429


def test_registrations_from_one_ip_are_limited(client: TestClient) -> None:
    assert register(client, email="one@example.com").status_code == 201
    assert register(client, email="two@example.com").status_code == 201

    blocked = register(client, email="three@example.com")

    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
