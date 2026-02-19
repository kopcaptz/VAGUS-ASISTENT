"""Тесты middleware rate limiting."""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
