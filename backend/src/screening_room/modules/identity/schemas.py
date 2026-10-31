"""Identity DTOs: API request/response models and the types other modules use."""

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from screening_room.core.security import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH

# --- API models -------------------------------------------------------------------


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    display_name: str | None = Field(default=None, max_length=100)


class LoginIn(BaseModel):
    email: EmailStr
    # No minimum: a too-short password just fails like any wrong password.
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class DeleteAccountIn(BaseModel):
    """Deleting an account needs the current password again (security.md §6)."""

    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class UserOut(BaseModel):
    email: str
    display_name: str | None


class SessionOut(BaseModel):
    """Who's signed in (null if nobody), and the CSRF token for unsafe requests."""

    user: UserOut | None
    csrf_token: str


# --- Internal DTOs (also the public surface for other modules) ---------------------


@dataclass(frozen=True)
class CurrentUser:
    """The signed-in user. A plain value, so it stays valid after a transaction
    ends (project-structure.md §5.2)."""

    id: int
    email: str
    display_name: str | None

    def to_out(self) -> UserOut:
        return UserOut(email=self.email, display_name=self.display_name)


@dataclass(frozen=True)
class AuthenticatedSession:
    """A valid session found from the request's session cookie."""

    user: CurrentUser
    token_hash: bytes
    expires_at: datetime


@dataclass(frozen=True)
class NewSession:
    """A just-created session. `token` is the raw value for the cookie."""

    token: str
    token_hash: bytes
    expires_at: datetime
