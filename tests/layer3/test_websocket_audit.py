"""Тесты audit logging для WebSocket."""

from datetime import datetime, timezone

import pytest
from fastapi import WebSocketDisconnect

from vagus.layer3.api.models import TaskStatus
from vagus.layer3.api.routers.tasks import task_store


def _task(task_id: str, status: TaskStatus, result=None, error=None):
    now = datetime.now(timezone.utc)
    task_store[task_id] = {
        "task_id": task_id,
        "status": status,
        "result": result,
        "error": error,
        "metadata": {},
        "created_at": now,
        "updated_at": now,
    }


def test_websocket_audit_endpoint_admin_only(client, user_headers):
    response = client.get("/api/v1/tasks/ws/audit-log", headers=user_headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


def test_websocket_audit_logs_lifecycle_events(client, admin_headers, admin_token):
    task_id = "ws-audit-completed"
    _task(task_id, TaskStatus.COMPLETED, result={"content": "audit-ok"})

    with client.websocket_connect(f"/api/v1/tasks/ws/{task_id}?token={admin_token}") as ws:
        payload = ws.receive_json()
        assert payload["done"] is True
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

    response = client.get(
        f"/api/v1/tasks/ws/audit-log?task_id={task_id}&limit=50",
        headers=admin_headers,
    )
    assert response.status_code == 200
    events = response.json()
    event_types = {entry["event_type"] for entry in events}

    assert "connect" in event_types
    assert "message_sent" in event_types
    assert "close" in event_types

    close_events = [entry for entry in events if entry["event_type"] == "close"]
    assert close_events
    assert close_events[0]["close_code"] == 1000
    assert close_events[0]["duration_seconds"] is not None


def test_websocket_audit_log_event_type_filter(client, admin_headers, admin_token):
    task_id = "ws-audit-filter"
    _task(task_id, TaskStatus.COMPLETED, result={"content": "filter-ok"})

    with client.websocket_connect(f"/api/v1/tasks/ws/{task_id}?token={admin_token}") as ws:
        ws.receive_json()
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()

    response = client.get(
        "/api/v1/tasks/ws/audit-log?event_type=connect&limit=100",
        headers=admin_headers,
    )
    assert response.status_code == 200
    events = response.json()
    assert events
    assert all(entry["event_type"] == "connect" for entry in events)
