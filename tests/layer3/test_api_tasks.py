"""Тесты роутера задач /api/v1/tasks/."""

import asyncio
import time
from datetime import datetime, timezone

import pytest
from vagus.layer3.api.models import TaskStatus
from vagus.layer3.api.routers.tasks import task_store


def test_create_task_success(client, admin_headers):
    resp = client.post(
        "/api/v1/tasks",
        json={"prompt": "Test prompt", "task_type": "default"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "pending"
    assert "/api/v1/tasks/" in data["status_endpoint"]
    assert "/ws/v1/tasks/" in data["stream_endpoint"]


def test_create_task_unauthorized(client):
    resp = client.post(
        "/api/v1/tasks",
        json={"prompt": "Test"},
    )
    assert resp.status_code == 401


def test_create_task_empty_prompt(client, admin_headers):
    resp = client.post(
        "/api/v1/tasks",
        json={"prompt": "", "task_type": "default"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


def test_create_task_with_metadata(client, admin_headers):
    resp = client.post(
        "/api/v1/tasks",
        json={"prompt": "Hello", "metadata": {"source": "test"}},
        headers=admin_headers,
    )
    assert resp.status_code == 201


def test_create_task_with_goal(client, admin_headers):
    resp = client.post(
        "/api/v1/tasks",
        json={
            "prompt": "Analyze the dataset",
            "goal": "Produce a summary report with actionable insights",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "pending"
    assert task_store[data["task_id"]]["metadata"].get("goal") == "Produce a summary report with actionable insights"


def test_get_task_status_found(client, admin_headers):
    create_resp = client.post(
        "/api/v1/tasks",
        json={"prompt": "Hello"},
        headers=admin_headers,
    )
    task_id = create_resp.json()["task_id"]

    resp = client.get(f"/api/v1/tasks/{task_id}", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["task_id"] == task_id
    assert "plan" in data
    assert "quality_score" in data
    assert "reflection_count" in data


def test_get_task_extra_fields_default_none(client, admin_headers):
    create_resp = client.post(
        "/api/v1/tasks",
        json={"prompt": "Simple task"},
        headers=admin_headers,
    )
    task_id = create_resp.json()["task_id"]

    resp = client.get(f"/api/v1/tasks/{task_id}", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] is None
    assert data["quality_score"] is None
    assert data["reflection_count"] is None


def test_get_task_returns_plan_quality_reflection(client, admin_headers):
    create_resp = client.post(
        "/api/v1/tasks",
        json={"prompt": "Task with metadata"},
        headers=admin_headers,
    )
    task_id = create_resp.json()["task_id"]

    task_store[task_id]["plan"] = {"steps": [{"step_id": "s1", "agent_type": "coder"}]}
    task_store[task_id]["quality_score"] = 0.85
    task_store[task_id]["reflection_count"] = 2

    resp = client.get(f"/api/v1/tasks/{task_id}", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] == {"steps": [{"step_id": "s1", "agent_type": "coder"}]}
    assert data["quality_score"] == 0.85
    assert data["reflection_count"] == 2


def test_get_task_status_not_found(client, admin_headers):
    resp = client.get("/api/v1/tasks/nonexistent-id", headers=admin_headers)
    assert resp.status_code == 404


def test_list_tasks(client, admin_headers):
    client.post("/api/v1/tasks", json={"prompt": "T1"}, headers=admin_headers)
    client.post("/api/v1/tasks", json={"prompt": "T2"}, headers=admin_headers)

    resp = client.get("/api/v1/tasks", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


def test_list_tasks_with_limit(client, admin_headers):
    for i in range(5):
        client.post("/api/v1/tasks", json={"prompt": f"T{i}"}, headers=admin_headers)

    resp = client.get("/api/v1/tasks?limit=2", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) <= 2


def test_cancel_task(client, admin_headers):
    create_resp = client.post(
        "/api/v1/tasks", json={"prompt": "Cancel me"}, headers=admin_headers
    )
    task_id = create_resp.json()["task_id"]

    # Force status to PENDING so cancel works (background task may have already completed)
    task_store[task_id]["status"] = TaskStatus.PENDING
    task_store[task_id]["result"] = None

    resp = client.delete(f"/api/v1/tasks/{task_id}", headers=admin_headers)
    assert resp.status_code == 204

    status_resp = client.get(f"/api/v1/tasks/{task_id}", headers=admin_headers)
    assert status_resp.json()["status"] == "failed"
    assert status_resp.json()["error"] == "Cancelled by user"


def test_cancel_nonexistent_task(client, admin_headers):
    resp = client.delete("/api/v1/tasks/ghost-id", headers=admin_headers)
    assert resp.status_code == 404


def test_cancel_completed_task(client, admin_headers):
    create_resp = client.post(
        "/api/v1/tasks", json={"prompt": "Done"}, headers=admin_headers
    )
    task_id = create_resp.json()["task_id"]
    task_store[task_id]["status"] = TaskStatus.COMPLETED
    task_store[task_id]["result"] = {"content": "done"}

    resp = client.delete(f"/api/v1/tasks/{task_id}", headers=admin_headers)
    assert resp.status_code == 400


def test_user_can_create_and_view_task(client, user_headers):
    resp = client.post(
        "/api/v1/tasks", json={"prompt": "User task"}, headers=user_headers
    )
    assert resp.status_code == 201
    task_id = resp.json()["task_id"]

    resp = client.get(f"/api/v1/tasks/{task_id}", headers=user_headers)
    assert resp.status_code == 200
