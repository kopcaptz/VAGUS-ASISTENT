"""Unit-тесты Dashboard: login, create_task, monitoring/metrics."""

from unittest.mock import MagicMock

import pytest
import httpx

from vagus.layer3.dashboard.dashboard import DashboardClient


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    request = httpx.Request("GET", "http://test:8000/")
    return httpx.Response(status_code=status_code, json=json_data or {}, request=request)


@pytest.fixture()
def dashboard() -> DashboardClient:
    return DashboardClient(base_url="http://test:8000")


def test_dashboard_login(dashboard: DashboardClient) -> None:
    """Аутентификация в Dashboard сохраняет access_token."""
    token_data = {
        "access_token": "dash-tok-abc",
        "refresh_token": "dash-ref-xyz",
        "token_type": "bearer",
    }

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.return_value = _mock_response(200, token_data)
    dashboard._http = mock_client

    result = dashboard.login("admin", "password")

    assert result["access_token"] == "dash-tok-abc"
    assert dashboard._token == "dash-tok-abc"
    mock_client.post.assert_called_once_with(
        "/auth/token",
        json={"username": "admin", "password": "password"},
    )


def test_dashboard_create_task(dashboard: DashboardClient) -> None:
    """Создание задачи через Dashboard UI client."""
    dashboard._token = "dash-tok-abc"
    task_data = {"task_id": "ui-task-1", "status": "pending"}

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.return_value = _mock_response(201, task_data)
    dashboard._http = mock_client

    result = dashboard.create_task("Analyze data", task_type="research")

    assert result["task_id"] == "ui-task-1"
    assert result["status"] == "pending"
    call_args = mock_client.post.call_args
    assert call_args[1]["headers"]["Authorization"] == "Bearer dash-tok-abc"
    assert call_args[1]["json"]["prompt"] == "Analyze data"


def test_dashboard_monitoring(dashboard: DashboardClient) -> None:
    """Отображение метрик через Dashboard."""
    dashboard._token = "dash-tok-abc"
    metrics = {"total_tasks": 42, "completed": 30, "pending": 12, "user": "admin"}

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = _mock_response(200, metrics)
    dashboard._http = mock_client

    result = dashboard.get_metrics()

    assert result["total_tasks"] == 42
    assert result["completed"] == 30
    assert result["pending"] == 12
    assert result["user"] == "admin"
    mock_client.get.assert_called_once_with(
        "/dashboard/metrics",
        headers={"Authorization": "Bearer dash-tok-abc"},
    )
