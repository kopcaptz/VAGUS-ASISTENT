"""
Тесты WebSocket эндпоинта /ws/tasks/{task_id} для real-time событий из Redis Streams.
"""

import pytest
from fastapi import WebSocketDisconnect

from vagus.layer3.api.websockets.task_events import (
    _matches_task,
    _should_forward,
    _to_client_message,
)


def _ws_url(task_id: str, token: str) -> str:
    return f"/ws/tasks/{task_id}?token={token}"


def test_task_events_websocket_requires_auth(client):
    """Без токена соединение закрывается с кодом 1008 (Policy Violation)."""
    with client.websocket_connect("/ws/tasks/any-task-id") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1008


def test_task_events_websocket_no_redis_closes_gracefully(client, admin_token):
    """При отсутствии Redis Streams соединение закрывается с 1011."""
    with client.websocket_connect(_ws_url("task-123", admin_token)) as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1011


def test_matches_task_by_api_task_id():
    """_matches_task возвращает True когда data.api_task_id совпадает."""
    msg = {"task_id": "plan_xyz", "data": {"api_task_id": "api-uuid-123", "plan_id": "plan_xyz"}}
    assert _matches_task(msg, "api-uuid-123") is True
    assert _matches_task(msg, "other") is False


def test_matches_task_by_task_id():
    """_matches_task возвращает True когда task_id совпадает."""
    msg = {"task_id": "plan_abc", "data": {}}
    assert _matches_task(msg, "plan_abc") is True
    assert _matches_task(msg, "plan_xyz") is False


def test_matches_task_data_as_json_string():
    """_matches_task парсит data как JSON-строку."""
    msg = {"task_id": "x", "data": '{"api_task_id": "match-me"}'}
    assert _matches_task(msg, "match-me") is True


def test_should_forward_event_types():
    """_should_forward возвращает True для task.planned, quality_gate.passed, agent.started."""
    assert _should_forward("task.planned", {}) is True
    assert _should_forward("quality_gate.passed", {}) is True
    assert _should_forward("agent.started", {}) is True
    assert _should_forward("reflection.triggered", {}) is True
    assert _should_forward("task.completed", {}) is False


def test_to_client_message_reflection_mapping():
    """agent.started с agent_type=reflection мапится в reflection.triggered."""
    msg = {"event": "agent.started", "task_id": "p1", "data": {"agent_type": "reflection"}, "ts": "1.0"}
    result = _to_client_message("agent.started", msg)
    assert result["event"] == "reflection.triggered"
    assert result["data"]["agent_type"] == "reflection"


def test_to_client_message_preserves_structure():
    """_to_client_message сохраняет event, task_id, data, ts."""
    msg = {"event": "task.planned", "task_id": "p1", "data": {"plan_id": "p1", "steps": ["s1"]}, "ts": "123"}
    result = _to_client_message("task.planned", msg)
    assert result["event"] == "task.planned"
    assert result["task_id"] == "p1"
    assert result["data"]["plan_id"] == "p1"
    assert result["data"]["steps"] == ["s1"]
    assert result["ts"] == "123"
