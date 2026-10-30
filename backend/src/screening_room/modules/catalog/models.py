"""ORM models for the catalog tables (data-model.md §3.2).

Private to this module: other modules use service.py and schemas.py instead.

Conventions (data-model.md §1): enum-like columns are `text` plus a named
CHECK constraint, provider IDs are stored as data (never as our primary keys),
and TMDB IDs are only unique per media type.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from screening_room.db import Base

# Allowed values of the enum-like columns, shared by the CHECK constraints.
PROVIDERS = ("tmdb",)
MEDIA_TYPES = ("movie", "tv")
DETAIL_LEVELS = ("summary", "full")
PROVIDER_STATUSES = ("active", "missing")
CREDIT_ROLES = ("cast", "director", "creator", "writer")
RUN_COMMANDS = ("ingest", "refresh")
RUN_STATUSES = ("running", "succeeded", "partial", "failed")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    """SQL for `column IN ('a', 'b')`, used in CHECK constraints."""
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def _timestamp() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


# --- Titles --------------------------------------------------------------------------


class Title(Base):
    """Every movie or TV show we know about, from any path (ingestion, detail
    read-through, search). Only some are in the candidate pool (service.py)."""

    __tablename__ = "titles"
    __table_args__ = (
        # The idempotency key for every upsert (ADR-0004).
        UniqueConstraint("provider", "media_type", "provider_id"),
        CheckConstraint(_one_of("provider", PROVIDERS), name="provider_valid"),
        CheckConstraint(_one_of("media_type", MEDIA_TYPES), name="media_type_valid"),
        CheckConstraint(_one_of("detail_level", DETAIL_LEVELS), name="detail_level_valid"),
        CheckConstraint(
            _one_of("provider_status", PROVIDER_STATUSES), name="provider_status_valid"
        ),
        CheckConstraint("runtime_minutes > 0", name="runtime_positive"),
        CheckConstraint(
            "media_type = 'tv' OR number_of_seasons IS NULL", name="seasons_only_for_tv"
        ),
        CheckConstraint("vote_average BETWEEN 0 AND 10", name="vote_average_range"),
        CheckConstraint("vote_count >= 0", name="vote_count_not_negative"),
        # A "full" title has, by definition, been hydrated at some point.
        CheckConstraint(
            "detail_level = 'summary' OR details_synced_at IS NOT NULL",
            name="full_has_details_synced_at",
        ),
        Index(None, "details_synced_at"),  # staleness scans
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    provider: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(Text)
    provider_id: Mapped[int] = mapped_column(Integer)
    imdb_id: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    original_name: Mapped[str | None] = mapped_column(Text)
    overview: Mapped[str | None] = mapped_column(Text)
    original_language: Mapped[str | None] = mapped_column(Text)  # ISO 639-1
    # Movie release date, or TV first air date.
    release_date: Mapped[date | None] = mapped_column(Date)
    # Movies: runtime. TV: typical episode runtime, when known.
    runtime_minutes: Mapped[int | None] = mapped_column(SmallInteger)
    number_of_seasons: Mapped[int | None] = mapped_column(SmallInteger)
    # Image paths only; URLs are built from configuration (ADR-0004).
    poster_path: Mapped[str | None] = mapped_column(Text)
    backdrop_path: Mapped[str | None] = mapped_column(Text)
    popularity: Mapped[float | None] = mapped_column(REAL)
    vote_average: Mapped[float | None] = mapped_column(REAL)
    vote_count: Mapped[int | None] = mapped_column(Integer)
    adult: Mapped[bool] = mapped_column(Boolean, server_default=false())
    detail_level: Mapped[str] = mapped_column(Text)
    provider_status: Mapped[str] = mapped_column(Text, server_default=text("'active'"))

    # Sync tracking (catalog-ingestion.md §9).
    first_ingested_at: Mapped[datetime] = _timestamp()
    summary_synced_at: Mapped[datetime] = _timestamp()
    details_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_error_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_sync_error: Mapped[str | None] = mapped_column(Text)
    last_sync_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# --- Genres ---------------------------------------------------------------------------


class Genre(Base):
    """Our internal genre taxonomy (catalog-ingestion.md §4.2), shared by movies and TV."""

    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True)  # e.g. "science-fiction"
    name: Mapped[str] = mapped_column(Text)


class ProviderGenreMap(Base):
    """Which internal genre(s) a provider genre means. One provider genre can map to
    several, e.g. TV "Sci-Fi & Fantasy" -> science-fiction + fantasy."""

    __tablename__ = "provider_genre_map"
    __table_args__ = (
        CheckConstraint(_one_of("provider", PROVIDERS), name="provider_valid"),
        CheckConstraint(_one_of("media_type", MEDIA_TYPES), name="media_type_valid"),
    )

    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    media_type: Mapped[str] = mapped_column(Text, primary_key=True)
    provider_genre_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    genre_id: Mapped[int] = mapped_column(ForeignKey("genres.id"), primary_key=True)


class TitleGenre(Base):
    __tablename__ = "title_genres"
    __table_args__ = (Index(None, "genre_id", "title_id"),)  # "titles in genre X"

    title_id: Mapped[int] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True
    )
    genre_id: Mapped[int] = mapped_column(
        ForeignKey("genres.id", ondelete="RESTRICT"), primary_key=True
    )
    # Provider order, for display only. Never a "primary genre" for ranking
    # (recommendation-engine.md §8).
    position: Mapped[int] = mapped_column(SmallInteger)


# --- People and credits ----------------------------------------------------------------


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (
        UniqueConstraint("provider", "provider_id"),
        CheckConstraint(_one_of("provider", PROVIDERS), name="provider_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    provider: Mapped[str] = mapped_column(Text)
    provider_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    profile_path: Mapped[str | None] = mapped_column(Text)


class TitleCredit(Base):
    """Top cast plus directors (movies) or creators (TV). Replaced wholesale on each
    hydration, so it needs no natural unique key (data-model.md §3.2)."""

    __tablename__ = "title_credits"
    __table_args__ = (CheckConstraint(_one_of("role", CREDIT_ROLES), name="role_valid"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="CASCADE"), index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id", ondelete="RESTRICT"))
    role: Mapped[str] = mapped_column(Text)
    character_name: Mapped[str | None] = mapped_column(Text)
    credit_order: Mapped[int] = mapped_column(SmallInteger)


# --- Provider recommendation lists ----------------------------------------------------


class ProviderTitleRecommendation(Base):
    """TMDB's "recommended" list for a title, for the favorite_neighbor signal.

    Targets are provider refs, NOT foreign keys: many aren't in our catalog. They're
    resolved at query time by joining on the titles unique key (data-model.md §3.2).
    """

    __tablename__ = "provider_title_recommendations"
    __table_args__ = (
        CheckConstraint(_one_of("provider", PROVIDERS), name="provider_valid"),
        CheckConstraint(_one_of("target_media_type", MEDIA_TYPES), name="target_media_type_valid"),
        CheckConstraint("provider_rank >= 1", name="provider_rank_positive"),
        # Resolving targets: "which titles recommend this provider ref?"
        # Named explicitly: the generated name would exceed PostgreSQL's 63-character
        # limit and be shortened with an unreadable hash suffix.
        Index(
            "ix_provider_title_recommendations_target",
            "provider",
            "target_media_type",
            "target_provider_id",
        ),
    )

    source_title_id: Mapped[int] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(Text, primary_key=True)
    target_media_type: Mapped[str] = mapped_column(Text, primary_key=True)
    target_provider_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_rank: Mapped[int] = mapped_column(SmallInteger)  # 1-based position
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # NULL when written by API read-through rather than an ingestion run.
    ingestion_run_id: Mapped[int | None] = mapped_column(
        # Named explicitly for the same 63-character reason as the index above.
        ForeignKey("ingestion_runs.id", name="fk_provider_title_recommendations_ingestion_run")
    )


# --- Ingestion runs and the candidate pool --------------------------------------------


class IngestionRun(Base):
    """One execution of `jobs ingest` or `jobs refresh`, for auditing (ADR-0005)."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        CheckConstraint(_one_of("command", RUN_COMMANDS), name="command_valid"),
        CheckConstraint(_one_of("status", RUN_STATUSES), name="status_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    command: Mapped[str] = mapped_column(Text)
    seed_plan_version: Mapped[str | None] = mapped_column(Text)  # e.g. "starter-v1"
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)  # CLI flags as executed
    status: Mapped[str] = mapped_column(Text)
    counts: Mapped[dict[str, Any]] = mapped_column(JSONB)
    started_at: Mapped[datetime] = _timestamp()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)


class CandidatePoolMembership(Base):
    """Why a title is in the pool: one row per seed source that returned it."""

    __tablename__ = "candidate_pool_memberships"
    __table_args__ = (
        CheckConstraint("source_rank >= 1", name="source_rank_positive"),
        Index(None, "source_key"),
    )

    title_id: Mapped[int] = mapped_column(
        ForeignKey("titles.id", ondelete="CASCADE"), primary_key=True
    )
    # Stable seed-source key, e.g. "movie:discover:genre=science-fiction".
    source_key: Mapped[str] = mapped_column(Text, primary_key=True)
    source_rank: Mapped[int] = mapped_column(Integer)  # position in that source's results
    first_seen_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"))
    last_seen_run_id: Mapped[int] = mapped_column(ForeignKey("ingestion_runs.id"))
