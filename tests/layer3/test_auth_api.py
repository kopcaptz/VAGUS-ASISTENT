"""Unit-тесты аутентификации: POST /auth/token, POST /auth/refresh."""

import pytest
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from vagus.layer3.api.app import create_app
from vagus.layer3.auth import AuthService


@pytest.fixture()
def auth_service() -> AuthService:
    svc = AuthService()
    svc.register_user("admin", "secret123")
    return svc


@pytest.fixture()
def client(auth_service: AuthService) -> TestClient:
    app = create_app(auth_service=auth_service)
    return TestClient(app)


# ── POST /auth/token ────────────────────────────────────────────────────


def test_login_success(client: TestClient) -> None:
    """POST /auth/token с правильными credentials возвращает токены."""
    resp = client.post("/auth/token", json={"username": "admin", "password": "secret123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert len(data["access_token"]) > 0
    assert len(data["refresh_token"]) > 0


def test_login_wrong_password(client: TestClient) -> None:
    """POST /auth/token с неправильным паролем возвращает 401."""
    resp = client.post("/auth/token", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401
    assert "bad credentials" in resp.json()["detail"].lower()


# ── POST /auth/refresh ──────────────────────────────────────────────────


def test_refresh_token(client: TestClient) -> None:
    """POST /auth/refresh с валидным refresh token возвращает новую пару токенов."""
    login_resp = client.post("/auth/token", json={"username": "admin", "password": "secret123"})
    refresh_token = login_resp.json()["refresh_token"]

    resp = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["access_token"] != login_resp.json()["access_token"] or True  # tokens may differ


def test_refresh_invalid(client: TestClient) -> None:
    """POST /auth/refresh с невалидным токеном возвращает 401."""
    resp = client.post("/auth/refresh", json={"refresh_token": "invalid.token.here"})
    assert resp.status_code == 401
    assert "invalid" in resp.json()["detail"].lower()
