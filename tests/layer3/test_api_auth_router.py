"""Тесты роутера аутентификации /api/v1/auth/."""

import pytest


def test_login_success(client):
    resp = client.post(
        "/api/v1/auth/token",
        json={"username": "admin", "password": "testpassword"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client):
    resp = client.post(
        "/api/v1/auth/token",
        json={"username": "admin", "password": "wrong"},
    )
    assert resp.status_code == 401


def test_login_unknown_user(client):
    resp = client.post(
        "/api/v1/auth/token",
        json={"username": "ghost", "password": "pass"},
    )
    assert resp.status_code == 401


def test_refresh_token_success(client):
    login_resp = client.post(
        "/api/v1/auth/token",
        json={"username": "admin", "password": "testpassword"},
    )
    refresh_tok = login_resp.json()["refresh_token"]

    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_tok},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data


def test_refresh_token_invalid(client):
    resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid.token.here"},
    )
    assert resp.status_code == 401
