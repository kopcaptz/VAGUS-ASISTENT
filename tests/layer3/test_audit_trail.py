"""Тесты audit trail storage, middleware и admin endpoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vagus.layer3.api.audit.audit_trail import AuditTrail
from vagus.layer3.api.middleware.audit_trail import AuditTrailMiddleware


def test_audit_trail_storage_insert_and_list(tmp_path):
    storage = AuditTrail(str(tmp_path / "audit.db"))
    storage.log_action(
        user_id="admin",
        action="api.request",
        resource="GET /health",
        details={"status_code": 200},
        ip_address="127.0.0.1",
    )
    rows = storage.list_logs(limit=10)
    assert len(rows) == 1
    assert rows[0]["action"] == "api.request"
    assert rows[0]["resource"] == "GET /health"


def test_audit_trail_middleware_logs_api_requests(tmp_path):
    app = FastAPI()
    app.state.audit_trail = AuditTrail(str(tmp_path / "audit-mw.db"))
    app.add_middleware(AuditTrailMiddleware)

    @app.get("/hello")
    async def hello():
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/hello?x=1")
        assert response.status_code == 200

    logs = app.state.audit_trail.list_logs(limit=20)
    assert logs
    assert logs[0]["action"] == "api.request"
    assert logs[0]["resource"] == "GET /hello"


def test_audit_trail_middleware_logs_cli_commands(tmp_path):
    app = FastAPI()
    app.state.audit_trail = AuditTrail(str(tmp_path / "audit-cli.db"))
    app.add_middleware(AuditTrailMiddleware)

    @app.get("/api/v1/status")
    async def status():
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/status",
            headers={
                "X-Vagus-CLI-Command": "admin.status",
                "X-Vagus-CLI-Arguments": "{\"verbose\": true}",
            },
        )
        assert response.status_code == 200

    logs = app.state.audit_trail.list_logs(limit=20)
    assert logs
    assert logs[0]["action"] == "cli.command"
    assert logs[0]["resource"] == "admin.status"


def test_admin_audit_logs_endpoint_requires_admin(client, user_headers):
    response = client.get("/api/v1/admin/audit-logs", headers=user_headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_admin_audit_logs_endpoint_returns_entries(app, client, admin_headers):
    app.state.audit_trail.log_action(
        user_id="admin",
        action="api.request",
        resource="GET /api/v1/status",
        details={"ok": True},
        ip_address="127.0.0.1",
    )

    response = client.get("/api/v1/admin/audit-logs?limit=10", headers=admin_headers)
    assert response.status_code == 200
    rows = response.json()
    assert rows
    assert rows[0]["action"] == "api.request"
