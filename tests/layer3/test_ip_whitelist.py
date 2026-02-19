"""Тесты IP whitelist middleware для admin endpoints."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vagus.layer3.api.middleware.ip_whitelist import IPWhitelistMiddleware


def _build_app(whitelist):
    app = FastAPI()
    app.add_middleware(
        IPWhitelistMiddleware,
        whitelist=whitelist,
        admin_path_prefix="/api/v1/admin/",
    )

    @app.get("/api/v1/admin/ping")
    async def admin_ping():
        return {"ok": True}

    @app.get("/api/v1/public")
    async def public():
        return {"ok": True}

    return app


def test_ip_whitelist_allows_admin_access_from_allowed_ip():
    app = _build_app(["127.0.0.1"])
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        resp = client.get("/api/v1/admin/ping")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_ip_whitelist_blocks_admin_access_from_disallowed_ip():
    app = _build_app(["127.0.0.1"])
    with TestClient(app, client=("10.10.10.10", 12345)) as client:
        resp = client.get("/api/v1/admin/ping")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Forbidden: IP not allowed"


def test_ip_whitelist_supports_cidr_ranges():
    app = _build_app(["192.168.1.0/24"])
    with TestClient(app, client=("192.168.1.55", 12345)) as client:
        resp = client.get("/api/v1/admin/ping")
    assert resp.status_code == 200


def test_ip_whitelist_applies_only_to_admin_paths():
    app = _build_app(["127.0.0.1"])
    with TestClient(app, client=("10.10.10.10", 12345)) as client:
        resp = client.get("/api/v1/public")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_ip_whitelist_empty_list_allows_all():
    app = _build_app([])
    with TestClient(app, client=("203.0.113.10", 12345)) as client:
        resp = client.get("/api/v1/admin/ping")
    assert resp.status_code == 200
