"""Application settings, read from environment variables (project-structure.md §6).

Values come from, in order of precedence:
1. real environment variables
2. the repository-root `.env` file (local development only; never committed)

Defaults are the safe production values. Local development relaxes the cookie
settings explicitly in .env, because browsers drop `Secure` cookies over http.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/screening_room/config.py -> parents[3] is the repository root.
_REPO_ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class _EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        # The shared .env also holds POSTGRES_* values for Docker Compose.
        extra="ignore",
    )


class DatabaseSettings(_EnvSettings):
    """Just the database URL: for tools that don't serve requests (migrations, tests)."""

    # e.g. postgresql+psycopg://user:password@127.0.0.1:5432/screening_room
    database_url: str


class TmdbSettings(_EnvSettings):
    """TMDB access (catalog-ingestion.md §10). Only ingestion and title detail need it,
    so it's optional here; code that calls TMDB fails clearly when it's missing."""

    # The "API Read Access Token" from themoviedb.org -> Settings -> API.
    tmdb_api_token: SecretStr | None = None
    # Requests per second, kept well below TMDB's published limits.
    tmdb_rate_limit_rps: float = Field(default=20.0, gt=0)

    def require_tmdb_token(self) -> str:
        if self.tmdb_api_token is None:
            raise RuntimeError(
                "TMDB_API_TOKEN is not set. Add your TMDB API Read Access Token to .env "
                "(see .env.example)."
            )
        return self.tmdb_api_token.get_secret_value()


class CatalogSettings(TmdbSettings):
    """Catalog freshness and ingestion tuning (initial values: catalog-ingestion.md §9-10)."""

    # Metadata older than this is stale and gets re-fetched.
    catalog_ttl_days: int = Field(default=14, gt=0)
    # Worker threads fetching details in parallel during ingestion.
    tmdb_max_workers: int = Field(default=8, gt=0, le=32)
    # We store image paths only and build URLs from this (ADR-0004).
    tmdb_image_base_url: str = "https://image.tmdb.org/t/p"


class JobSettings(DatabaseSettings, CatalogSettings):
    """What the ingestion CLI needs: database and TMDB, but none of the web app's secrets."""


class Settings(DatabaseSettings, CatalogSettings):
    """Everything the web app needs."""

    # --- Required: the app refuses to start without these rather than guessing ---

    # HMAC key for CSRF tokens (security.md §5). SecretStr keeps it out of reprs
    # and logs. Rotating it only forces clients to fetch a new token.
    csrf_secret: SecretStr = Field(min_length=32)

    # Origins allowed to make unsafe requests, as a JSON list in the environment:
    # ALLOWED_ORIGINS=["http://localhost:5173"]
    allowed_origins: list[str] = Field(min_length=1)

    # --- Optional ---------------------------------------------------------------

    session_ttl_days: int = Field(default=30, gt=0)  # absolute session lifetime
    cookie_secure: bool = True  # send cookies over HTTPS only
    cookie_prefix_host: bool = True  # use __Host- cookie names (requires Secure)

    @property
    def session_cookie_name(self) -> str:
        return "__Host-sr_session" if self.cookie_prefix_host else "sr_session"

    @property
    def csrf_cookie_name(self) -> str:
        return "__Host-sr_csrf" if self.cookie_prefix_host else "sr_csrf"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once on first use."""
    return Settings()


def get_app_settings(request: Request) -> Settings:
    """FastAPI dependency: the settings this app was created with.

    Use this in request code rather than get_settings(), so an app built with
    other settings (as tests do) is honoured.
    """
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
