"""Тесты WebSocket стриминга."""

from datetime import datetime, timezone

import pytest
from vagus.layer3.api.models import TaskStatus
from vagus.layer3.api.routers.tasks import task_store


def test_websocket_task_not_found(client):
    with client.websocket_connect("/api/v1/tasks/ws/nonexistent") as ws:
        data = ws.receive_json()
        assert data["error"] == "Task not found"
        assert data["done"] is True


def test_websocket_completed_task(client):
    now = datetime.now(timezone.utc)
    task_store["ws-test-1"] = {
        "task_id": "ws-test-1",
        "status": TaskStatus.COMPLETED,
        "result": {"content": "WS result"},
        "error": None,
        "metadata": {},
        "created_at": now,
        "updated_at": now,
    }

    with client.websocket_connect("/api/v1/tasks/ws/ws-test-1") as ws:
        data = ws.receive_json()
        assert data["done"] is True
        assert "WS result" in data["content"]


def test_websocket_failed_task(client):
    now = datetime.now(timezone.utc)
    task_store["ws-test-2"] = {
        "task_id": "ws-test-2",
        "status": TaskStatus.FAILED,
        "result": None,
        "error": "Something broke",
        "metadata": {},
        "created_at": now,
        "updated_at": now,
    }

    with client.websocket_connect("/api/v1/tasks/ws/ws-test-2") as ws:
        data = ws.receive_json()
        assert data["done"] is True
        assert data["error"] == "Something broke"
