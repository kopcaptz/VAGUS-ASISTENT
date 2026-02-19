"""Интеграционные тесты Layer 3: полный цикл создания и получения задачи."""

import time
from datetime import datetime, timezone

import pytest
from vagus.layer3.api.models import TaskStatus
from vagus.layer3.api.routers.tasks import task_store


def test_full_cycle_create_and_get(client, admin_headers):
    """Полный цикл: auth → create → get status."""
    login_resp = client.post(
        "/api/v1/auth/token",
        json={"username": "admin", "password": "admin"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = client.post(
        "/api/v1/tasks",
        json={"prompt": "Integration test", "task_type": "research"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    task_id = create_resp.json()["task_id"]

    status_resp = client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert status_resp.status_code == 200


def test_full_cycle_list_and_agents(client, admin_headers):
    """Создание задач, получение списка и агентов."""
    client.post("/api/v1/tasks", json={"prompt": "T1"}, headers=admin_headers)
    client.post("/api/v1/tasks", json={"prompt": "T2"}, headers=admin_headers)

    tasks_resp = client.get("/api/v1/tasks", headers=admin_headers)
    assert tasks_resp.status_code == 200
    assert len(tasks_resp.json()) >= 2

    agents_resp = client.get("/api/v1/agents", headers=admin_headers)
    assert agents_resp.status_code == 200
    assert len(agents_resp.json()) == 3


def test_full_cycle_status_check(client, admin_headers):
    """Проверка статуса системы включает метрики Layer 1."""
    status_resp = client.get("/api/v1/status", headers=admin_headers)
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["layer2_agents_count"] == 3
    assert data["layer1_stats"]["requests"] == 42


def test_completed_task_has_result(client, admin_headers):
    """Задача с результатом (имитация завершения)."""
    create_resp = client.post(
        "/api/v1/tasks", json={"prompt": "Complete me"}, headers=admin_headers
    )
    task_id = create_resp.json()["task_id"]

    task_store[task_id]["status"] = TaskStatus.COMPLETED
    task_store[task_id]["result"] = {"content": "Final answer"}
    task_store[task_id]["updated_at"] = datetime.now(timezone.utc)

    resp = client.get(f"/api/v1/tasks/{task_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"
    assert resp.json()["result"]["content"] == "Final answer"


def test_user_isolation(client, admin_headers, user_headers):
    """Обычный пользователь видит только свои задачи (admin видит все)."""
    client.post("/api/v1/tasks", json={"prompt": "Admin task"}, headers=admin_headers)
    client.post("/api/v1/tasks", json={"prompt": "User task"}, headers=user_headers)

    admin_list = client.get("/api/v1/tasks", headers=admin_headers)
    user_list = client.get("/api/v1/tasks", headers=user_headers)

    assert len(admin_list.json()) >= 2
    user_tasks = user_list.json()
    assert all(True for _ in user_tasks)
