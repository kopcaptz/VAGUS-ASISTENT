"""Тесты middleware rate limiting."""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vagus.layer3.api.auth import create_access_token
from vagus.layer3.api.middleware.rate_limit import RateLimitMiddleware


def test_rate_limit_allows_normal_traffic():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, max_requests=10, window_seconds=60)

    @app.get("/test")
    async def endpoint():
        return {"ok": True}

    with TestClient(app) as client:
        for _ in range(10):
            resp = client.get("/test")
            assert resp.status_code == 200


def test_rate_limit_blocks_excess_traffic():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, max_requests=5, window_seconds=60)

    @app.get("/test")
    async def endpoint():
        return {"ok": True}

    with TestClient(app) as client:
        for _ in range(5):
            client.get("/test")

        resp = client.get("/test")
        assert resp.status_code == 429
        assert resp.json()["detail"] == "Rate limit exceeded"


def test_rate_limit_middleware_init():
    app = FastAPI()
    mw = RateLimitMiddleware(app, max_requests=100, window_seconds=30)
    assert mw.max_requests == 100
    assert mw.window_seconds == 30


def test_role_based_rate_limit_for_anonymous():
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        window_seconds=60,
        anonymous_requests_per_minute=2,
        user_requests_per_minute=5,
        admin_requests_per_minute=10,
    )

    @app.get("/test")
    async def endpoint():
        return {"ok": True}

    with TestClient(app) as client:
        assert client.get("/test").status_code == 200
        assert client.get("/test").status_code == 200
        blocked = client.get("/test")
        assert blocked.status_code == 429


def test_role_based_rate_limit_for_user():
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        window_seconds=60,
        anonymous_requests_per_minute=1,
        user_requests_per_minute=3,
        admin_requests_per_minute=10,
    )
    user_token = create_access_token({"sub": "user-a", "role": "user"})

    @app.get("/test")
    async def endpoint():
        return {"ok": True}

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {user_token}"}
        assert client.get("/test", headers=headers).status_code == 200
        assert client.get("/test", headers=headers).status_code == 200
        assert client.get("/test", headers=headers).status_code == 200
        blocked = client.get("/test", headers=headers)
        assert blocked.status_code == 429


def test_role_based_rate_limit_for_admin():
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        window_seconds=60,
        anonymous_requests_per_minute=1,
        user_requests_per_minute=2,
        admin_requests_per_minute=4,
    )
    admin_token = create_access_token({"sub": "admin-a", "role": "admin"})

    @app.get("/test")
    async def endpoint():
        return {"ok": True}

    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {admin_token}"}
        for _ in range(4):
            assert client.get("/test", headers=headers).status_code == 200
        blocked = client.get("/test", headers=headers)
        assert blocked.status_code == 429
