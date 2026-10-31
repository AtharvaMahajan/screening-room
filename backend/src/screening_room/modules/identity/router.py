"""Auth endpoints (ADR-0007, security.md §3 and §5).

Handlers own the transaction: each write handler commits once, after the
service calls succeed and before returning (project-structure.md §5).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from screening_room.config import Settings, SettingsDep
from screening_room.core.errors import AppError
from screening_room.db import SessionDep
from screening_room.modules.identity import csrf, service
from screening_room.modules.identity.dependencies import AuthDep, CurrentUserDep, get_current_user
from screening_room.modules.identity.schemas import (
    AuthenticatedSession,
    CurrentUser,
    DeleteAccountIn,
    LoginIn,
    NewSession,
    RegisterIn,
    SessionOut,
)

router = APIRouter(prefix="/api/auth")
# The signed-in user's account itself (security.md §6).
account_router = APIRouter(prefix="/api/me", dependencies=[Depends(get_current_user)])


@router.get("/session")
def read_session(
    request: Request, response: Response, auth: AuthDep, settings: SettingsDep
) -> SessionOut:
    """Who's signed in, plus a CSRF token for the current session (or "anon").

    The SPA calls this on startup and after a csrf_failed error (security.md §5.2).
    Read-only: the only side effect is (re)setting the CSRF cookie.
    """
    binding = csrf.binding_for(auth)
    secret = settings.csrf_secret.get_secret_value()
    token = request.cookies.get(settings.csrf_cookie_name, "")
    if not csrf.is_valid_csrf_token(secret, binding, token):
        token = csrf.mint_csrf_token(secret, binding)
        _set_csrf_cookie(response, settings, token, auth.expires_at if auth else None)
    return SessionOut(user=auth.user.to_out() if auth else None, csrf_token=token)


@router.post("/register", status_code=201)
def register(
    body: RegisterIn, response: Response, session: SessionDep, auth: AuthDep, settings: SettingsDep
) -> SessionOut:
    user = service.register_user(session, body.email, body.password, body.display_name)
    new_session = _replace_session(session, auth, user, settings)
    session.commit()
    return _signed_in(response, settings, user, new_session)


@router.post("/login")
def login(
    body: LoginIn, response: Response, session: SessionDep, auth: AuthDep, settings: SettingsDep
) -> SessionOut:
    user = service.authenticate(session, body.email, body.password)
    if user is None:
        # One message for unknown email and wrong password (security.md §2).
        raise AppError(401, "invalid_credentials", "Invalid email or password.")
    new_session = _replace_session(session, auth, user, settings)
    session.commit()
    return _signed_in(response, settings, user, new_session)


@router.post("/logout")
def logout(
    response: Response, session: SessionDep, auth: AuthDep, settings: SettingsDep
) -> SessionOut:
    """Revoke the session (if any), clear its cookie, and hand back an anonymous token."""
    if auth is not None:
        service.revoke_session(session, auth.token_hash)
        session.commit()
    return _signed_out(response, settings)


@account_router.delete("")
def delete_account(
    body: DeleteAccountIn,
    response: Response,
    session: SessionDep,
    user: CurrentUserDep,
    settings: SettingsDep,
) -> SessionOut:
    """Delete your account and all your data, for good (FR-01, security.md §6).

    Needs the session-bound CSRF token (like every write) and your password.
    Signs you out: both cookies are cleared, as on logout.
    """
    service.delete_account(session, user.id, body.password)
    session.commit()
    return _signed_out(response, settings)


# --- Helpers ------------------------------------------------------------------------


def _replace_session(
    session: Session, auth: AuthenticatedSession | None, user: CurrentUser, settings: Settings
) -> NewSession:
    """Always start a fresh session; revoke one the request already carried.

    Never reusing a presented session prevents session fixation (security.md §3).
    """
    if auth is not None:
        service.revoke_session(session, auth.token_hash)
    return service.create_session(session, user.id, settings.session_ttl_days)


def _signed_out(response: Response, settings: Settings) -> SessionOut:
    """Clear the session cookie and rotate to an anonymous CSRF token."""
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    token = csrf.mint_csrf_token(settings.csrf_secret.get_secret_value(), csrf.ANONYMOUS_BINDING)
    _set_csrf_cookie(response, settings, token, expires_at=None)
    return SessionOut(user=None, csrf_token=token)


def _signed_in(
    response: Response, settings: Settings, user: CurrentUser, new_session: NewSession
) -> SessionOut:
    """Set both cookies and rotate the CSRF token to one bound to the new session."""
    response.set_cookie(
        settings.session_cookie_name,
        new_session.token,
        max_age=_seconds_until(new_session.expires_at),
        path="/",
        secure=settings.cookie_secure,
        httponly=True,  # page scripts can never read the session token
        samesite="lax",
    )
    token = csrf.mint_csrf_token(
        settings.csrf_secret.get_secret_value(), new_session.token_hash.hex()
    )
    _set_csrf_cookie(response, settings, token, new_session.expires_at)
    return SessionOut(user=user.to_out(), csrf_token=token)


def _set_csrf_cookie(
    response: Response, settings: Settings, token: str, expires_at: datetime | None
) -> None:
    response.set_cookie(
        settings.csrf_cookie_name,
        token,
        # Lives as long as the session; anonymous tokens last for the browser session.
        max_age=_seconds_until(expires_at) if expires_at else None,
        path="/",
        secure=settings.cookie_secure,
        httponly=False,  # the double-submit copy: readable, useless without the session
        samesite="lax",
    )


def _seconds_until(moment: datetime) -> int:
    return max(0, int((moment - datetime.now(UTC)).total_seconds()))
