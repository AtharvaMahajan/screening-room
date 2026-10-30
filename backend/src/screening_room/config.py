"""Application settings, read from environment variables (project-structure.md §6).

Values come from, in order of precedence:
1. real environment variables
2. the repository-root `.env` file (local development only; never committed)

Settings are added here as features need them. M1a only needs the database URL.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/src/screening_room/config.py -> parents[3] is the repository root.
_REPO_ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        # The shared .env also holds POSTGRES_* values for Docker Compose.
        extra="ignore",
    )

    # Required: the app refuses to start without it rather than guessing a default.
    # Example: postgresql+psycopg://user:password@localhost:5432/screening_room
    database_url: str


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once on first use."""
    return Settings()
