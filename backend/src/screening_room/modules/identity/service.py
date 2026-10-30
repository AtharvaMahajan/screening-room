"""Identity use cases: accounts and sessions (security.md §2–3).

Services never commit (project-structure.md §5.1): the route handler does,
once, after the service call succeeds.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from screening_room.core.errors import AppError
from screening_room.core.security import (
    hash_password,
    hash_session_token,
    new_session_token,
    password_needs_rehash,
    verify_password,
)
from screening_room.modules.identity.models import User, UserSession
from screening_room.modules.identity.schemas import AuthenticatedSession, CurrentUser, NewSession


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _to_current_user(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, email=user.email, display_name=user.display_name)


def register_user(
    session: Session, email: str, password: str, display_name: str | None
) -> CurrentUser:
    user = User(
        email=normalize_email(email),
        password_hash=hash_password(password),
        display_name=display_name,
    )
    session.add(user)
    try:
        # Flush now so a duplicate email surfaces here, as a domain error.
        session.flush()
    except IntegrityError:
        # Deliberately vague (security.md §2), though the 409 itself does tell
        # the caller the email is taken; that's unavoidable without email
        # verification.
        raise AppError(409, "email_unavailable", "This email can't be used.") from None
    return _to_current_user(user)


def authenticate(session: Session, email: str, password: str) -> CurrentUser | None:
    """The user if email and password match, else None (never says which was wrong)."""
    user = session.scalar(select(User).where(User.email == normalize_email(email)))
    if not verify_password(user.password_hash if user else None, password):
        return None
    assert user is not None  # verify_password(None, ...) is always False
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)  # saved by the handler's commit
    return _to_current_user(user)


def create_session(session: Session, user_id: int, ttl_days: int) -> NewSession:
    token = new_session_token()
    token_hash = hash_session_token(token)
    expires_at = datetime.now(UTC) + timedelta(days=ttl_days)
    session.add(UserSession(user_id=user_id, token_hash=token_hash, expires_at=expires_at))
    session.flush()
    return NewSession(token=token, token_hash=token_hash, expires_at=expires_at)


def revoke_session(session: Session, token_hash: bytes) -> None:
    session.execute(
        update(UserSession)
        .where(UserSession.token_hash == token_hash, UserSession.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )


def resolve_session(session: Session, token: str) -> AuthenticatedSession | None:
    """The valid session for a cookie token, or None if unknown, revoked or expired.

    Read-only, so it can run in every request's shared transaction (ADR-0007).
    """
    row = session.execute(
        select(User, UserSession.token_hash, UserSession.expires_at)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == hash_session_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > func.now(),
        )
    ).first()
    if row is None:
        return None
    user, token_hash, expires_at = row
    return AuthenticatedSession(
        user=_to_current_user(user), token_hash=token_hash, expires_at=expires_at
    )
