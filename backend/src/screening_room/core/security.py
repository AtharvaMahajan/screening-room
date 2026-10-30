"""Password hashing and token primitives (security.md §2–3).

Kept free of HTTP and database code so it's easy to test and reason about.
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# Argon2id with the library's current recommended parameters (security.md §2).
_password_hasher = PasswordHasher()

# Verified against when the email doesn't exist, so a failed login takes about
# as long either way and response timing doesn't reveal which emails exist.
_DUMMY_HASH = _password_hasher.hash("not-a-real-password")

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """True if the password matches. Pass None when the user doesn't exist."""
    if password_hash is None:
        # Do the same (slow) work as a real check, then fail.
        _check(_DUMMY_HASH, password)
        return False
    return _check(password_hash, password)


def _check(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerificationError, InvalidHashError:
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True when the hash was made with older parameters (rehash on login)."""
    return _password_hasher.check_needs_rehash(password_hash)


def new_session_token() -> str:
    """A 256-bit random token from a CSPRNG, URL-safe base64 encoded."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> bytes:
    """SHA-256 of the token: the only form stored in the database.

    A fast hash is right here, unlike for passwords: the token is 256 random
    bits, so there's nothing to brute-force, and every request looks it up.
    """
    return hashlib.sha256(token.encode()).digest()
