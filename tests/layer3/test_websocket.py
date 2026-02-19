"""Unit-тесты WebSocket: подключение, обновления статуса, финальный результат."""

import asyncio

import pytest
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from vagus.layer3.api.app import create_app
from vagus.layer3.auth import AuthService


@pytest.fixture()
def auth_service() -> AuthService:
    svc = AuthService()
    svc.register_user("wsuser", "wspass")
    return svc


@pytest.fixture()
def mock_orchestrator() -> AsyncMock:
    orch = AsyncMock()
    orch.execute_task = AsyncMock(return_value={
        "content": "done!",
        "metadata": {"agent": "researcher"},
    })
    return orch


@pytest.fixture()
def client(auth_service: AuthService, mock_orchestrator: AsyncMock) -> TestClient:
    app = create_app(auth_service=auth_service, orchestrator=mock_orchestrator)
    return TestClient(app)


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    resp = client.post("/auth/token", json={"username": "wsuser", "password": "wspass"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_websocket_connection(client: TestClient) -> None:
    """WebSocket подключается к /ws/{task_id} и принимает соединение."""
    with client.websocket_connect("/ws/test-task-1") as ws:
        assert ws is not None


def test_websocket_updates(client: TestClient, auth_headers: dict[str, str]) -> None:
    """WebSocket получает обновление статуса при создании задачи."""
    create_resp = client.post("/tasks", json={"prompt": "ws test"}, headers=auth_headers)
    task_id = create_resp.json()["task_id"]

    with client.websocket_connect(f"/ws/{task_id}") as ws:
        msg = ws.receive_json()
        assert msg["task_id"] == task_id
        assert msg["status"] in ("pending", "in_progress", "completed")


def test_websocket_task_completed(
    client: TestClient,
    auth_headers: dict[str, str],
    mock_orchestrator: AsyncMock,
) -> None:
    """WebSocket получает текущий статус задачи после подключения."""
    create_resp = client.post("/tasks", json={"prompt": "final check"}, headers=auth_headers)
    task_id = create_resp.json()["task_id"]

    with client.websocket_connect(f"/ws/{task_id}") as ws:
        msg = ws.receive_json()
        assert "task_id" in msg
        assert "status" in msg
        assert msg["task_id"] == task_id
