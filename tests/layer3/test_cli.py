"""Unit-тесты CLI: login, create_task, status."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import httpx

from vagus.layer3.cli.cli import VagusCLI


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    return tmp_path / ".vagus" / "config.json"


@pytest.fixture()
def cli(config_path: Path) -> VagusCLI:
    return VagusCLI(base_url="http://test:8000", config_path=config_path)


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> httpx.Response:
    request = httpx.Request("GET", "http://test:8000/")
    return httpx.Response(status_code=status_code, json=json_data or {}, request=request)


def test_cli_login(cli: VagusCLI, config_path: Path) -> None:
    """Команда login сохраняет конфиг с токенами."""
    token_data = {
        "access_token": "acc-tok-123",
        "refresh_token": "ref-tok-456",
        "token_type": "bearer",
    }

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.return_value = _mock_response(200, token_data)
    cli._http = mock_client

    result = cli.login("user", "pass")

    assert result["access_token"] == "acc-tok-123"
    assert config_path.exists()

    saved = json.loads(config_path.read_text())
    assert saved["access_token"] == "acc-tok-123"
    assert saved["refresh_token"] == "ref-tok-456"


def test_cli_create_task(cli: VagusCLI) -> None:
    """Создание задачи через CLI возвращает task_id."""
    cli._token = "test-access-token"
    task_response = {"task_id": "task-001", "status": "pending"}

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.post.return_value = _mock_response(201, task_response)
    cli._http = mock_client

    result = cli.create_task("Write unit tests")

    assert result["task_id"] == "task-001"
    assert result["status"] == "pending"
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    assert call_kwargs[1]["headers"]["Authorization"] == "Bearer test-access-token"


def test_cli_status(cli: VagusCLI) -> None:
    """Получение статуса задачи через CLI."""
    status_response = {"task_id": "task-001", "status": "completed"}

    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.return_value = _mock_response(200, status_response)
    cli._http = mock_client

    result = cli.get_status("task-001")

    assert result["task_id"] == "task-001"
    assert result["status"] == "completed"
    mock_client.get.assert_called_once_with("/tasks/task-001")
