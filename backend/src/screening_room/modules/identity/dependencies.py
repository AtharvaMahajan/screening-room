"""Request dependencies for authentication. `CurrentUserDep` is the public one."""

from typing import Annotated

from fastapi import Depends, Request

from screening_room.config import SettingsDep
from screening_room.core.errors import AppError
from screening_room.core.logging import bind
from screening_room.db import SessionDep
from screening_room.modules.identity import service
from screening_room.modules.identity.schemas import AuthenticatedSession, CurrentUser


def get_auth(
    request: Request, session: SessionDep, settings: SettingsDep
) -> AuthenticatedSession | None:
    """The request's valid session, if any.

    FastAPI caches a dependency's result per request, so the CSRF check and
    CurrentUserDep share this one lookup.
    """
    token = request.cookies.get(settings.session_cookie_name)
    auth = service.resolve_session(session, token) if token else None
    if auth is not None:
        bind(user_id=auth.user.id)  # on this request's log lines: an id, never the email
    return auth


AuthDep = Annotated[AuthenticatedSession | None, Depends(get_auth)]


def get_current_user(auth: AuthDep) -> CurrentUser:
    """Require a signed-in user. Runs after the CSRF check (security.md §5.3)."""
    if auth is None:
        raise AppError(401, "unauthenticated", "Sign in to continue.")
    return auth.user


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
