"""
Unit tests for the Tasks REST API.
"""

import time

import pytest

from vagus.layer3.api.routers.tasks import _task_store


class TestCreateTask:

    def test_create_task_success(self, client, auth_headers):
        response = client.post(
            "/api/v1/tasks",
            json={"prompt": "Test request", "task_type": "default"},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert "/api/v1/tasks/" in data["status_endpoint"]
        assert "/ws/v1/tasks/" in data["stream_endpoint"]

    def test_create_task_unauthorized(self, client):
        response = client.post(
            "/api/v1/tasks",
            json={"prompt": "Test request"},
        )
        assert response.status_code == 401

    def test_create_task_invalid_token(self, client):
        response = client.post(
            "/api/v1/tasks",
            json={"prompt": "Test request"},
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    def test_create_task_empty_prompt(self, client, auth_headers):
        response = client.post(
            "/api/v1/tasks",
            json={"prompt": "", "task_type": "default"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_create_task_no_prompt(self, client, auth_headers):
        response = client.post(
            "/api/v1/tasks",
            json={"task_type": "default"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_create_task_with_metadata(self, client, auth_headers):
        response = client.post(
            "/api/v1/tasks",
            json={
                "prompt": "Test with metadata",
                "task_type": "research",
                "metadata": {"source": "test"},
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["task_id"]


class TestGetTaskStatus:

    def test_get_task_status_found(self, client, auth_headers):
        create_resp = client.post(
            "/api/v1/tasks",
            json={"prompt": "Test request"},
            headers=auth_headers,
        )
        task_id = create_resp.json()["task_id"]

        response = client.get(
            f"/api/v1/tasks/{task_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert data["status"] in ("pending", "in_progress", "completed", "failed")

    def test_get_task_status_not_found(self, client, auth_headers):
        response = client.get(
            "/api/v1/tasks/nonexistent-id",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestListTasks:

    def test_list_tasks_empty(self, client, auth_headers):
        response = client.get("/api/v1/tasks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["tasks"] == []
        assert data["total"] == 0

    def test_list_tasks_after_create(self, client, auth_headers):
        client.post(
            "/api/v1/tasks",
            json={"prompt": "Task 1"},
            headers=auth_headers,
        )
        client.post(
            "/api/v1/tasks",
            json={"prompt": "Task 2"},
            headers=auth_headers,
        )

        response = client.get("/api/v1/tasks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["tasks"]) == 2


class TestCancelTask:

    def test_cancel_task(self, client, auth_headers):
        create_resp = client.post(
            "/api/v1/tasks",
            json={"prompt": "Task to cancel"},
            headers=auth_headers,
        )
        task_id = create_resp.json()["task_id"]

        response = client.delete(
            f"/api/v1/tasks/{task_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

    def test_cancel_nonexistent_task(self, client, auth_headers):
        response = client.delete(
            "/api/v1/tasks/nonexistent",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestHealthCheck:

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
