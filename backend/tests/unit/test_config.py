import pytest
from pydantic import ValidationError

from screening_room.config import Settings

VALID_ENV = {
    "DATABASE_URL": "postgresql+psycopg://u:p@db:5432/sr",
    "CSRF_SECRET": "x" * 32,
    "ALLOWED_ORIGINS": '["http://localhost:5173"]',
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name, value in VALID_ENV.items():
        monkeypatch.setenv(name, value)
    for name in ("SESSION_TTL_DAYS", "COOKIE_SECURE", "COOKIE_PREFIX_HOST"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def load() -> Settings:
    # _env_file=None: ignore any local .env so the test only sees the environment.
    return Settings(_env_file=None)


def test_reads_settings_from_environment(env: pytest.MonkeyPatch) -> None:
    settings = load()

    assert settings.database_url == VALID_ENV["DATABASE_URL"]
    assert settings.csrf_secret.get_secret_value() == "x" * 32
    assert settings.allowed_origins == ["http://localhost:5173"]


def test_defaults_are_the_production_safe_values(env: pytest.MonkeyPatch) -> None:
    settings = load()

    assert settings.session_ttl_days == 30
    assert settings.cookie_secure is True
    assert settings.session_cookie_name == "__Host-sr_session"
    assert settings.csrf_cookie_name == "__Host-sr_csrf"


def test_local_development_cookie_names(env: pytest.MonkeyPatch) -> None:
    env.setenv("COOKIE_PREFIX_HOST", "false")

    settings = load()

    assert (settings.session_cookie_name, settings.csrf_cookie_name) == ("sr_session", "sr_csrf")


def test_secret_never_appears_in_repr(env: pytest.MonkeyPatch) -> None:
    assert "x" * 32 not in repr(load())


@pytest.mark.parametrize("missing", ["DATABASE_URL", "CSRF_SECRET", "ALLOWED_ORIGINS"])
def test_required_settings_are_enforced(env: pytest.MonkeyPatch, missing: str) -> None:
    env.delenv(missing)

    with pytest.raises(ValidationError, match=missing.lower()):
        load()


@pytest.mark.parametrize(
    ("name", "value"),
    [("CSRF_SECRET", "too-short"), ("ALLOWED_ORIGINS", "[]"), ("SESSION_TTL_DAYS", "0")],
)
def test_unsafe_values_are_rejected(env: pytest.MonkeyPatch, name: str, value: str) -> None:
    env.setenv(name, value)

    with pytest.raises(ValidationError):
        load()
