"""Fixtures shared by unit and integration tests."""

import pytest

from screening_room.config import Settings

# TestClient sends requests to http://testserver, so that's the allowed origin.
TEST_ORIGIN = "http://testserver"


def make_test_settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,  # tests never read the developer's .env
        database_url=database_url,
        csrf_secret="test-csrf-secret-that-is-at-least-32-characters",
        allowed_origins=[TEST_ORIGIN],
        cookie_secure=False,  # TestClient talks plain http
        cookie_prefix_host=False,
    )


@pytest.fixture
def settings() -> Settings:
    """Settings for tests that never connect to the database.

    tests/integration/conftest.py overrides this with the real database URL.
    """
    # Never connected to: SQLAlchemy engines connect lazily.
    return make_test_settings("postgresql+psycopg://unused:unused@localhost:1/unused")
