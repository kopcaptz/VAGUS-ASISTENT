"""Тесты WebSocket hardening: close codes, heartbeat и лимиты."""

from datetime import datetime, timezone

import pytest
from fastapi import WebSocketDisconnect

from vagus.layer3.api.models import TaskStatus
from vagus.layer3.api.routers.tasks import task_store
from vagus.layer3.api.websocket_security import WebSocketRuntimeSettings


def _ws_url(task_id: str, token: str) -> str:
    return f"/api/v1/tasks/ws/{task_id}?token={token}"


def _set_websocket_settings(app, **overrides):
    defaults = WebSocketRuntimeSettings()
    app.state.websocket_settings = WebSocketRuntimeSettings(
        max_message_size_mb=overrides.get("max_message_size_mb", defaults.max_message_size_mb),
        ping_interval_seconds=overrides.get("ping_interval_seconds", defaults.ping_interval_seconds),
        ping_timeout_seconds=overrides.get("ping_timeout_seconds", defaults.ping_timeout_seconds),
        max_messages_per_minute=overrides.get(
            "max_messages_per_minute", defaults.max_messages_per_minute
        ),
        status_poll_interval_seconds=overrides.get(
            "status_poll_interval_seconds", defaults.status_poll_interval_seconds
        ),
    )


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


def test_websocket_invalid_token_closed_with_1008(client):
    with client.websocket_connect("/api/v1/tasks/ws/any-task") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1008


def test_websocket_task_not_found_closed_normally(client, admin_token):
    with client.websocket_connect(_ws_url("nonexistent", admin_token)) as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1000


def test_websocket_completed_task_returns_result_and_closes_1000(client, admin_token):
    _task("ws-test-completed", TaskStatus.COMPLETED, result={"content": "WS result"})

    with client.websocket_connect(_ws_url("ws-test-completed", admin_token)) as ws:
        data = ws.receive_json()
        assert data["done"] is True
        assert "WS result" in data["content"]

        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1000


def test_websocket_failed_task_closes_with_1011(client, admin_token):
    _task("ws-test-failed", TaskStatus.FAILED, error="Something broke")

    with client.websocket_connect(_ws_url("ws-test-failed", admin_token)) as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1011


def test_websocket_heartbeat_sends_ping_and_accepts_pong(client, app, admin_token):
    _set_websocket_settings(
        app,
        ping_interval_seconds=1,
        ping_timeout_seconds=4,
        status_poll_interval_seconds=0.2,
    )
    _task("ws-test-heartbeat", TaskStatus.PENDING)

    with client.websocket_connect(_ws_url("ws-test-heartbeat", admin_token)) as ws:
        got_ping = False
        for _ in range(20):
            message = ws.receive_json()
            if message.get("type") == "ping":
                got_ping = True
                ws.send_json({"type": "pong"})
                break
        assert got_ping is True

        next_message = ws.receive_json()
        assert next_message.get("type") == "ping" or "done" in next_message


def test_websocket_closes_on_pong_timeout(client, app, admin_token):
    _set_websocket_settings(
        app,
        ping_interval_seconds=1,
        ping_timeout_seconds=2,
        status_poll_interval_seconds=0.2,
    )
    _task("ws-test-timeout", TaskStatus.PENDING)

    with client.websocket_connect(_ws_url("ws-test-timeout", admin_token)) as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            for _ in range(30):
                ws.receive_json()
    assert exc.value.code == 1000


def test_websocket_rate_limit_closes_with_1013(client, app, admin_token):
    _set_websocket_settings(
        app,
        max_messages_per_minute=5,
        ping_interval_seconds=10,
        ping_timeout_seconds=20,
        status_poll_interval_seconds=0.2,
    )
    _task("ws-test-rate-limit", TaskStatus.PENDING)

    with client.websocket_connect(_ws_url("ws-test-rate-limit", admin_token)) as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            for _ in range(20):
                ws.send_text("pong")
                ws.receive_json()
    assert exc.value.code == 1013


def test_websocket_message_too_big_closes_with_1009(client, app, admin_token):
    _set_websocket_settings(
        app,
        max_message_size_mb=1,
        ping_interval_seconds=10,
        ping_timeout_seconds=20,
        status_poll_interval_seconds=0.2,
    )
    _task("ws-test-big-message", TaskStatus.PENDING)
    huge_message = "x" * (1024 * 1024 + 16)

    with client.websocket_connect(_ws_url("ws-test-big-message", admin_token)) as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.send_text(huge_message)
            ws.receive_json()
    assert exc.value.code == 1009
