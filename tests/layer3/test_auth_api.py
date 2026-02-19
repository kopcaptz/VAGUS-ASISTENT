"""
Unit tests for the Auth REST API.
"""

import pytest


class TestAuthToken:

    def test_login_success(self, client):
        response = client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        response = client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "wrong"},
        )
        assert response.status_code == 401

    def test_login_unknown_user(self, client):
        response = client.post(
            "/api/v1/auth/token",
            data={"username": "nobody", "password": "pass"},
        )
        assert response.status_code == 401


class TestRefreshToken:

    def test_refresh_success(self, client):
        login_resp = client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "admin"},
        )
        refresh_token = login_resp.json()["refresh_token"]

        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    def test_refresh_invalid_token(self, client):
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid-token"},
        )
        assert response.status_code == 401
