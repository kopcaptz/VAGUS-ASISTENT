"""Тесты CLI команд (Typer)."""

from __future__ import annotations

import pytest
import typer
from typer.testing import CliRunner

from vagus.layer3.cli import app as cli_app_module
from vagus.layer3.cli.commands import admin as admin_cmd
from vagus.layer3.cli.commands import agent as agent_cmd
from vagus.layer3.cli.commands import task as task_cmd


class _FakeClient:
    def __init__(self):
        self.status_calls = 0

    def create_task(self, prompt: str, task_type: str = "default"):
        return {"task_id": "task-1"}

    def get_task_status(self, task_id: str):
        self.status_calls += 1
        if self.status_calls < 2:
            return {"status": "in_progress"}
        return {"status": "completed", "result": {"content": "done"}}

    def list_tasks(self, limit: int = 10):
        return [{"task_id": "t1", "status": "completed", "created_at": "now"}]

    def get_agents(self):
        return [
            {
                "name": "researcher",
                "description": "research agent",
                "task_types": ["research"],
                "is_available": True,
            }
        ]

    def get_system_status(self):
        return {"requests": 5, "uptime_seconds": 10}


def test_cli_root_help():
    runner = CliRunner()
    result = runner.invoke(cli_app_module.app, ["--help"])
    assert result.exit_code == 0
    assert "task" in result.output
    assert "agent" in result.output
    assert "admin" in result.output


def test_cli_login_command(monkeypatch):
    runner = CliRunner()
    saved = {}

    monkeypatch.setattr(cli_app_module, "save_config", lambda data: saved.update(data))
    monkeypatch.setattr(cli_app_module, "print_success", lambda _msg: None)

    result = runner.invoke(
        cli_app_module.app,
        ["login", "--api-url", "http://localhost:9999", "--api-key", "secret-token"],
    )
    assert result.exit_code == 0
    assert saved["api_url"] == "http://localhost:9999"
    assert saved["api_key"] == "secret-token"


def test_task_create_wait_false(monkeypatch):
    fake = _FakeClient()
    calls = []

    monkeypatch.setattr(task_cmd, "CLIApiClient", lambda: fake)
    monkeypatch.setattr(task_cmd, "print_success", lambda msg: calls.append(("success", msg)))
    monkeypatch.setattr(task_cmd, "print_info", lambda msg: calls.append(("info", msg)))
    monkeypatch.setattr(task_cmd, "print_error", lambda msg: calls.append(("error", msg)))

    task_cmd.create_task(prompt="hello", task_type="default", wait=False)
    assert any("Задача создана" in msg for typ, msg in calls if typ == "success")


def test_task_create_wait_completed(monkeypatch):
    fake = _FakeClient()
    printed = []

    monkeypatch.setattr(task_cmd, "CLIApiClient", lambda: fake)
    monkeypatch.setattr(task_cmd, "print_success", lambda msg: printed.append(msg))
    monkeypatch.setattr(task_cmd, "print_info", lambda _msg: None)
    monkeypatch.setattr(task_cmd, "print_error", lambda _msg: None)
    monkeypatch.setattr(task_cmd.time, "sleep", lambda _s: None)

    task_cmd.create_task(prompt="hello", task_type="default", wait=True)
    assert any("выполнена" in msg.lower() for msg in printed)


def test_task_create_wait_failed(monkeypatch):
    class _FailClient(_FakeClient):
        def get_task_status(self, task_id: str):
            return {"status": "failed", "error": "boom"}

    monkeypatch.setattr(task_cmd, "CLIApiClient", lambda: _FailClient())
    monkeypatch.setattr(task_cmd, "print_success", lambda _msg: None)
    monkeypatch.setattr(task_cmd, "print_info", lambda _msg: None)
    monkeypatch.setattr(task_cmd, "print_error", lambda _msg: None)
    monkeypatch.setattr(task_cmd.time, "sleep", lambda _s: None)

    with pytest.raises(typer.Exit):
        task_cmd.create_task(prompt="hello", task_type="default", wait=True)


def test_task_status_and_list(monkeypatch):
    fake = _FakeClient()
    captured = {}

    monkeypatch.setattr(task_cmd, "CLIApiClient", lambda: fake)
    monkeypatch.setattr(task_cmd, "print_dict", lambda title, data: captured.setdefault("dict", (title, data)))
    monkeypatch.setattr(
        task_cmd,
        "print_table",
        lambda title, columns, rows: captured.setdefault("table", (title, columns, rows)),
    )
    monkeypatch.setattr(task_cmd, "print_error", lambda _msg: None)

    task_cmd.get_status("task-1")
    task_cmd.list_tasks(limit=1)

    assert captured["dict"][0].startswith("Задача")
    assert captured["table"][0] == "Список задач"


def test_agent_and_admin_commands(monkeypatch):
    fake = _FakeClient()
    captured = {}

    monkeypatch.setattr(agent_cmd, "CLIApiClient", lambda: fake)
    monkeypatch.setattr(admin_cmd, "CLIApiClient", lambda: fake)
    monkeypatch.setattr(
        agent_cmd,
        "print_table",
        lambda title, columns, rows: captured.setdefault("agents", (title, columns, rows)),
    )
    monkeypatch.setattr(
        admin_cmd,
        "print_dict",
        lambda title, data: captured.setdefault("status", (title, data)),
    )
    monkeypatch.setattr(agent_cmd, "print_error", lambda _msg: None)
    monkeypatch.setattr(admin_cmd, "print_error", lambda _msg: None)

    agent_cmd.list_agents()
    admin_cmd.system_status()

    assert captured["agents"][0] == "Агенты"
    assert captured["status"][0] == "Статус системы"
