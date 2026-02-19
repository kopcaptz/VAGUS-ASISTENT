"""Тесты JWT-аутентификации."""

import time

import pytest
from vagus.layer3.api.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)


def test_create_and_decode_access_token():
    token = create_access_token({"sub": "admin", "role": "admin"})
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "admin"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token():
    token = create_refresh_token({"sub": "user", "role": "user"})
    payload = decode_refresh_token(token)
    assert payload is not None
    assert payload["sub"] == "user"
    assert payload["type"] == "refresh"


def test_decode_access_rejects_refresh():
    token = create_refresh_token({"sub": "admin"})
    assert decode_access_token(token) is None


def test_decode_refresh_rejects_access():
    token = create_access_token({"sub": "admin"})
    assert decode_refresh_token(token) is None


def test_decode_invalid_token():
    assert decode_token("invalid.token.here") is None
    assert decode_token("") is None
    assert decode_token("abc") is None


def test_decode_tampered_token():
    token = create_access_token({"sub": "admin"})
    parts = token.split(".")
    parts[1] = parts[1] + "x"
    tampered = ".".join(parts)
    assert decode_token(tampered) is None


def test_verify_password():
    assert verify_password("admin", get_password_hash("admin")) is True
    assert verify_password("wrong", get_password_hash("admin")) is False


def test_get_password_hash_deterministic():
    h1 = get_password_hash("test")
    h2 = get_password_hash("test")
    assert h1 == h2


def test_authenticate_user_success():
    result = authenticate_user("admin", "admin")
    assert result is not None
    assert result["sub"] == "admin"
    assert result["role"] == "admin"


def test_authenticate_user_wrong_password():
    assert authenticate_user("admin", "wrongpass") is None


def test_authenticate_user_unknown():
    assert authenticate_user("nonexistent", "pass") is None


def test_token_has_expiration():
    token = create_access_token({"sub": "admin"})
    payload = decode_token(token)
    assert "exp" in payload
    assert payload["exp"] > time.time()


def test_token_has_issued_at():
    token = create_access_token({"sub": "admin"})
    payload = decode_token(token)
    assert "iat" in payload
