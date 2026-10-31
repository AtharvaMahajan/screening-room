"""ORM models for recommendation logging (data-model.md §3.4). Private to this module.

Every request and its results are stored: they explain any past result and
feed evaluation (recommendation-engine.md §13). Result events arrive in M4.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from screening_room.db import Base


class RecRequest(Base):
    __tablename__ = "rec_requests"
    # "A user's requests, newest first": PostgreSQL reads a B-tree index in either
    # direction, so a plain (user_id, created_at) index serves DESC order too.
    __table_args__ = (Index(None, "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # CASCADE: deleting a user deletes their recommendation logs (data-model.md §6).
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # media_type, genre_ids, max_runtime_minutes, count of excluded ids
    context: Mapped[dict[str, Any]] = mapped_column(JSONB)
    engine_version: Mapped[str] = mapped_column(Text)
    config_hash: Mapped[str] = mapped_column(Text)
    pool_size: Mapped[int] = mapped_column(Integer)
    candidate_count: Mapped[int] = mapped_column(Integer)
    eligible_count: Mapped[int] = mapped_column(Integer)
    anchor_count: Mapped[int] = mapped_column(SmallInteger)
    anchors_without_neighbors: Mapped[int] = mapped_column(SmallInteger)
    cold_start: Mapped[bool] = mapped_column(Boolean)
    diversity_relaxed: Mapped[bool] = mapped_column(Boolean)
    latency_ms: Mapped[int] = mapped_column(Integer)  # retrieval + engine, server-side


class RecResult(Base):
    __tablename__ = "rec_results"
    __table_args__ = (
        UniqueConstraint("request_id", "rank"),
        UniqueConstraint("request_id", "title_id"),
        CheckConstraint("rank >= 1", name="rank_positive"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("rec_requests.id", ondelete="CASCADE"))
    # RESTRICT: catalog rows that users' data references are never deleted.
    title_id: Mapped[int] = mapped_column(ForeignKey("titles.id", ondelete="RESTRICT"))
    rank: Mapped[int] = mapped_column(SmallInteger)
    score: Mapped[float] = mapped_column(REAL)  # rounded final score
    # Per-signal value, weighted contribution, and the favorite_neighbor source.
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # as shown to the user
