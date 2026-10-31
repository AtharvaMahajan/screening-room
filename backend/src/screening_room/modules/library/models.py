"""ORM models for the library tables (data-model.md §3.5). Private to this module.

One table per relationship (ADR-0008): they have different keys, cardinalities
and lifecycles, and a title can be in several at once (e.g. rated and not for me).

Every table has an optional rec_result_id: the recommendation the action came
from, when it came from one (M4c). SET NULL, so attribution never blocks deletion.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from screening_room.db import Base


def _user_id(*, primary_key: bool = False) -> Mapped[int]:
    # CASCADE: deleting a user deletes their library (data-model.md §6).
    return mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=primary_key)


def _title_id(*, primary_key: bool = False) -> Mapped[int]:
    # RESTRICT: catalog rows that users reference are never deleted.
    return mapped_column(ForeignKey("titles.id", ondelete="RESTRICT"), primary_key=primary_key)


def _rec_result_id() -> Mapped[int | None]:
    return mapped_column(ForeignKey("rec_results.id", ondelete="SET NULL"))


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class WatchlistItem(Base):
    """Saved to watch later. The primary key makes duplicates impossible (FR-05)."""

    __tablename__ = "watchlist_items"
    __table_args__ = (Index(None, "user_id", "added_at"),)

    user_id: Mapped[int] = _user_id(primary_key=True)
    title_id: Mapped[int] = _title_id(primary_key=True)
    added_at: Mapped[datetime] = _now()
    rec_result_id: Mapped[int | None] = _rec_result_id()


class ViewingEvent(Base):
    """One viewing. Several per title are allowed: rewatches (FR-06)."""

    __tablename__ = "viewing_events"
    __table_args__ = (
        Index(None, "user_id", "title_id"),
        Index(None, "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = _user_id()
    title_id: Mapped[int] = _title_id()
    watched_on: Mapped[date | None] = mapped_column(Date)  # optional: "I watched it" is enough
    created_at: Mapped[datetime] = _now()
    rec_result_id: Mapped[int | None] = _rec_result_id()


class Rating(Base):
    """The user's current 1-5★ rating of a title (ADR-0009)."""

    __tablename__ = "ratings"
    __table_args__ = (CheckConstraint("value BETWEEN 1 AND 5", name="value_range"),)

    user_id: Mapped[int] = _user_id(primary_key=True)
    title_id: Mapped[int] = _title_id(primary_key=True)
    value: Mapped[int] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()
    rec_result_id: Mapped[int | None] = _rec_result_id()


class TitleFeedback(Base):
    """Explicit negative feedback. Only "not_for_me" for now: a persisted
    "not now" can be added later by widening the CHECK (data-model.md §7)."""

    __tablename__ = "title_feedback"
    __table_args__ = (CheckConstraint("kind IN ('not_for_me')", name="kind_valid"),)

    user_id: Mapped[int] = _user_id(primary_key=True)
    title_id: Mapped[int] = _title_id(primary_key=True)
    kind: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _now()
    rec_result_id: Mapped[int | None] = _rec_result_id()
