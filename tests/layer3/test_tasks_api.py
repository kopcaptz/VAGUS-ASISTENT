"""Unit-тесты REST API задач: POST /tasks, GET /tasks/{id}, rate limit."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from vagus.layer3.api.app import create_app
from vagus.layer3.auth import AuthService


@pytest.fixture()
def auth_service() -> AuthService:
    svc = AuthService()
    svc.register_user("testuser", "testpass")
    return svc


@pytest.fixture()
def mock_orchestrator() -> AsyncMock:
    orch = AsyncMock()
    orch.execute_task = AsyncMock(return_value={
        "content": "result text",
        "metadata": {"agent": "researcher"},
    })
    return orch


@pytest.fixture()
def client(auth_service: AuthService, mock_orchestrator: AsyncMock) -> TestClient:
    app = create_app(auth_service=auth_service, orchestrator=mock_orchestrator)
    return TestClient(app)


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    resp = client.post("/auth/token", json={"username": "testuser", "password": "testpass"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── POST /tasks ──────────────────────────────────────────────────────────


def test_create_task_success(client: TestClient, auth_headers: dict[str, str]) -> None:
    """POST /tasks с валидным JWT возвращает 201 и task_id."""
    resp = client.post("/tasks", json={"prompt": "Hello world"}, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "pending"


def test_create_task_unauthorized(client: TestClient) -> None:
    """POST /tasks без JWT возвращает 401 (или 403 от HTTPBearer)."""
    resp = client.post("/tasks", json={"prompt": "Hello"})
    assert resp.status_code in (401, 403)


def test_create_task_empty_prompt(client: TestClient, auth_headers: dict[str, str]) -> None:
    """POST /tasks с пустым prompt возвращает 422 (validation error)."""
    resp = client.post("/tasks", json={"prompt": ""}, headers=auth_headers)
    assert resp.status_code == 422


# ── GET /tasks/{id} ─────────────────────────────────────────────────────


def test_get_task_status_found(client: TestClient, auth_headers: dict[str, str]) -> None:
    """GET /tasks/{id} возвращает корректный статус для существующей задачи."""
    create_resp = client.post("/tasks", json={"prompt": "some task"}, headers=auth_headers)
    task_id = create_resp.json()["task_id"]

    resp = client.get(f"/tasks/{task_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == task_id
    assert data["status"] in ("pending", "in_progress", "completed")


def test_get_task_status_not_found(client: TestClient) -> None:
    """GET /tasks/{несуществующий_id} возвращает 404."""
    resp = client.get("/tasks/nonexistent-id-12345")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ── Rate Limit ───────────────────────────────────────────────────────────


def test_rate_limit(client: TestClient, auth_headers: dict[str, str]) -> None:
    """61-й запрос подряд возвращает 429 (rate limit exceeded)."""
    for i in range(60):
        resp = client.post("/tasks", json={"prompt": f"task {i}"}, headers=auth_headers)
        assert resp.status_code == 201, f"Request {i+1} unexpectedly failed with {resp.status_code}"

    resp = client.post("/tasks", json={"prompt": "one too many"}, headers=auth_headers)
    assert resp.status_code == 429
    assert "rate limit" in resp.json()["detail"].lower()
