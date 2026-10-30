"""ORM models for the identity tables (data-model.md §3.1).

Private to this module: other modules use service.py and schemas.py instead.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    LargeBinary,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from screening_room.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Uniqueness only works if every write path normalizes the email, so the
        # database enforces it rather than trusting the application.
        CheckConstraint("email = lower(btrim(email))", name="email_normalized"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        CheckConstraint("octet_length(token_hash) = 32", name="token_hash_is_sha256"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # CASCADE: deleting a user deletes their sessions (account deletion, M4).
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # SHA-256 of the session token. The raw token only ever exists in the cookie.
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
