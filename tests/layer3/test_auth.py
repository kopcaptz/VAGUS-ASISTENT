"""Тесты JWT-аутентификации."""

import time

import pytest
from vagus.layer3.api.auth import (
    authenticate_user,
    configure_jwt_secret_rotation,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    decode_token,
    force_rotate_jwt_secret,
    get_jwt_rotation_state,
    get_password_hash,
    _set_current_jwt_secret_for_tests,
    verify_password,
)


def test_create_and_decode_access_token():
    token = create_access_token({"sub": "testpassword", "role": "testpassword"})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "testpassword"
    assert payload["role"] == "testpassword"
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token():
    token = create_refresh_token({"sub": "user", "role": "user"})
    payload = decode_refresh_token(token)
    assert payload is not None
    assert payload["sub"] == "user"
    assert payload["type"] == "refresh"


def test_decode_access_rejects_refresh():
    token = create_refresh_token({"sub": "testpassword"})
    assert decode_access_token(token) is None


def test_decode_refresh_rejects_access():
    token = create_access_token({"sub": "testpassword"})
    assert decode_refresh_token(token) is None


def test_decode_invalid_token():
    assert decode_token("invalid.token.here") is None
    assert decode_token("") is None
    assert decode_token("abc") is None


def test_decode_tampered_token():
    token = create_access_token({"sub": "testpassword"})
    parts = token.split(".")
    parts[1] = parts[1] + "x"
    tampered = ".".join(parts)
    assert decode_token(tampered) is None


def test_verify_password():
    assert verify_password("testpassword", get_password_hash("testpassword")) is True
    assert verify_password("wrong", get_password_hash("testpassword")) is False



def test_authenticate_user_success():
    result = authenticate_user("testpassword", "testpassword")
    assert result is not None
    assert result["sub"] == "testpassword"
    assert result["role"] == "testpassword"


def test_authenticate_user_wrong_password():
    assert authenticate_user("testpassword", "wrongpass") is None


def test_authenticate_user_unknown():
    assert authenticate_user("nonexistent", "pass") is None


def test_token_has_expiration():
    token = create_access_token({"sub": "testpassword"})
    payload = decode_token(token)
    assert "exp" in payload
    assert payload["exp"] > time.time()


def test_token_has_issued_at():
    token = create_access_token({"sub": "testpassword"})
    payload = decode_token(token)
    assert "iat" in payload


def test_jwt_rotation_keeps_old_tokens_valid_after_force_rotate():
    configure_jwt_secret_rotation(secret_rotation_days=30, max_old_secrets=3)
    _set_current_jwt_secret_for_tests("test-secret-before-rotation")

    token = create_access_token({"sub": "testpassword", "role": "testpassword"})
    assert decode_access_token(token) is not None

    force_rotate_jwt_secret()
    # Старый токен остаётся валиден благодаря истории секретов.
    assert decode_access_token(token) is not None


def test_jwt_rotation_happens_automatically_by_age():
    configure_jwt_secret_rotation(secret_rotation_days=30, max_old_secrets=3)
    _set_current_jwt_secret_for_tests(
        "expired-secret",
        created_at_ts=time.time() - (31 * 24 * 60 * 60),
    )
    _ = create_access_token({"sub": "testpassword"})
    state = get_jwt_rotation_state()
    assert state["old_secrets_count"] >= 1


def test_jwt_rotation_caps_old_secret_history():
    configure_jwt_secret_rotation(secret_rotation_days=30, max_old_secrets=2)
    _set_current_jwt_secret_for_tests("seed-secret")
    for _ in range(5):
        force_rotate_jwt_secret()
    state = get_jwt_rotation_state()
    assert state["old_secrets_count"] <= 2
