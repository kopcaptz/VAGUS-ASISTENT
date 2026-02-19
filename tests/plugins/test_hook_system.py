"""Tests for plugin hook system."""

from __future__ import annotations

import pytest

from vagus.plugins.hooks import HookSystem


@pytest.mark.asyncio
async def test_pre_task_execution_respects_priority_order():
    hook_system = HookSystem()

    def low_priority(task: dict) -> dict:
        updated = dict(task)
        updated["steps"] = updated.get("steps", []) + ["low"]
        return updated

    def high_priority(task: dict) -> dict:
        updated = dict(task)
        updated["steps"] = updated.get("steps", []) + ["high"]
        return updated

    hook_system.register_hook("pre_task_execution", low_priority, priority=10)
    hook_system.register_hook("pre_task_execution", high_priority, priority=90)

    result = await hook_system.pre_task_execution({"steps": []})
    assert result["steps"] == ["high", "low"]


@pytest.mark.asyncio
async def test_post_task_execution_supports_async_and_sync_hooks():
    hook_system = HookSystem()

    def sync_hook(_: dict, result: dict) -> dict:
        updated = dict(result)
        updated["value"] += 1
        updated["flow"].append("sync")
        return updated

    async def async_hook(_: dict, result: dict) -> dict:
        updated = dict(result)
        updated["value"] *= 2
        updated["flow"].append("async")
        return updated

    hook_system.register_hook("post_task_execution", sync_hook, priority=30)
    hook_system.register_hook("post_task_execution", async_hook, priority=80)

    result = await hook_system.post_task_execution({}, {"value": 2, "flow": []})
    assert result["value"] == 5
    assert result["flow"] == ["async", "sync"]


@pytest.mark.asyncio
async def test_on_error_invokes_registered_hooks():
    hook_system = HookSystem()
    captured: list[str] = []

    def error_handler(_: dict, error: Exception) -> None:
        captured.append(str(error))

    hook_system.register_hook("on_error", error_handler, priority=50)
    await hook_system.on_error({"id": "task-1"}, RuntimeError("boom"))

    assert captured == ["boom"]


def test_register_hook_rejects_unknown_hook_name():
    hook_system = HookSystem()

    with pytest.raises(ValueError):
        hook_system.register_hook("unknown_hook", lambda *_: None)
