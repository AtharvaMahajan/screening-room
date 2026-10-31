"""ORM models for the profile tables (data-model.md §3.3). Private to this module."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from screening_room.db import Base


class UserGenrePreference(Base):
    """One stance per user and genre: liked, or avoided."""

    __tablename__ = "user_genre_preferences"
    __table_args__ = (CheckConstraint("stance IN ('like', 'avoid')", name="stance_valid"),)

    # CASCADE: deleting a user deletes their preferences (data-model.md §6).
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    genre_id: Mapped[int] = mapped_column(ForeignKey("genres.id"), primary_key=True)
    stance: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserFavoriteTitle(Base):
    """A title the user picked as a favorite. Profile data, NOT a rating: it doesn't
    imply the user would rate it 5★, and creates no viewing event (data-model.md §3.3)."""

    __tablename__ = "user_favorite_titles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    # RESTRICT: catalog rows that users reference are never deleted.
    title_id: Mapped[int] = mapped_column(
        ForeignKey("titles.id", ondelete="RESTRICT"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
