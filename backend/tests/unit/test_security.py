from screening_room.core.security import (
    hash_password,
    hash_session_token,
    new_session_token,
    password_needs_rehash,
    verify_password,
)


def test_password_hash_is_argon2id_and_never_the_password() -> None:
    hashed = hash_password("correct horse battery")

    assert hashed.startswith("$argon2id$")
    assert "correct horse battery" not in hashed


def test_same_password_hashes_differently_each_time() -> None:
    # Random salt: equal passwords can't be spotted by comparing hashes.
    assert hash_password("correct horse battery") != hash_password("correct horse battery")


def test_verify_password() -> None:
    hashed = hash_password("correct horse battery")

    assert verify_password(hashed, "correct horse battery") is True
    assert verify_password(hashed, "wrong password!!") is False


def test_verify_password_for_unknown_user_is_false() -> None:
    assert verify_password(None, "anything at all") is False


def test_verify_password_with_corrupt_hash_is_false() -> None:
    assert verify_password("not-a-hash", "correct horse battery") is False


def test_fresh_hash_does_not_need_rehash() -> None:
    assert password_needs_rehash(hash_password("correct horse battery")) is False


def test_session_tokens_are_long_random_and_unique() -> None:
    tokens = {new_session_token() for _ in range(100)}

    assert len(tokens) == 100
    # 32 random bytes -> 43 URL-safe base64 characters (256 bits).
    assert all(len(token) == 43 for token in tokens)


def test_session_token_hash_is_32_byte_sha256() -> None:
    token = new_session_token()

    assert len(hash_session_token(token)) == 32  # matches the DB CHECK constraint
    assert hash_session_token(token) == hash_session_token(token)
    assert hash_session_token(token) != hash_session_token(new_session_token())
