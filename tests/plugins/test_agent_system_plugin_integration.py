"""Integration tests for plugin hooks inside TaskOrchestrator."""

from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from vagus.layer2 import CommunicationLayer, TaskOrchestrator
from vagus.layer2.agents.base_agent import BaseAgent
from vagus.plugins.hooks import HookSystem


class _EchoAgent(BaseAgent):
    def __init__(self, name: str, accepted_task_type: str, *, should_fail: bool = False):
        super().__init__(name=name, llm_router=None, description="test agent")
        self.accepted_task_type = accepted_task_type
        self.should_fail = should_fail
        self.last_task: Optional[Dict[str, Any]] = None

    def can_handle(self, task_type: str) -> bool:
        return task_type == self.accepted_task_type

    async def process(self, task: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.last_task = task
        if self.should_fail:
            raise RuntimeError("agent boom")
        return {
            "success": True,
            "content": task.get("prompt", ""),
            "metadata": task.get("metadata", {}),
        }


@pytest.mark.asyncio
async def test_orchestrator_applies_pre_and_post_plugin_hooks():
    hooks = HookSystem()

    def pre_hook(task: dict) -> dict:
        updated = dict(task)
        updated["prompt"] = f"[pre] {updated['prompt']}"
        return updated

    def post_hook(_: dict, result: dict) -> dict:
        updated = dict(result)
        updated["plugin_processed"] = True
        return updated

    hooks.register_hook("pre_task_execution", pre_hook, priority=80)
    hooks.register_hook("post_task_execution", post_hook, priority=80)

    orchestrator = TaskOrchestrator(
        communication=CommunicationLayer(),
        plugin_hook_system=hooks,
    )
    agent = _EchoAgent(name="default_agent", accepted_task_type="default")
    orchestrator.register_agent(agent)

    result = await orchestrator.execute_task("task-1", "hello", task_type="default")
    assert result["plugin_processed"] is True
    assert result["content"].startswith("[pre] hello")


@pytest.mark.asyncio
async def test_orchestrator_error_hook_invoked_on_failure():
    hooks = HookSystem()
    captured: list[str] = []

    def error_hook(task: dict, error: Exception) -> None:
        captured.append(f"{task['task_id']}:{error}")

    hooks.register_hook("on_error", error_hook, priority=50)

    orchestrator = TaskOrchestrator(
        communication=CommunicationLayer(),
        plugin_hook_system=hooks,
    )
    orchestrator.register_agent(_EchoAgent(name="broken", accepted_task_type="default", should_fail=True))

    result = await orchestrator.execute_task("task-2", "boom", task_type="default")
    assert "error" in result
    assert captured and captured[0].startswith("task-2:")


@pytest.mark.asyncio
async def test_pre_hook_can_redirect_task_type_to_another_agent():
    hooks = HookSystem()

    def redirect_hook(task: dict) -> dict:
        updated = dict(task)
        updated["task_type"] = "analysis"
        return updated

    hooks.register_hook("pre_task_execution", redirect_hook, priority=90)

    orchestrator = TaskOrchestrator(
        communication=CommunicationLayer(),
        plugin_hook_system=hooks,
    )
    default_agent = _EchoAgent(name="default_agent", accepted_task_type="default")
    analyst_agent = _EchoAgent(name="analyst_agent", accepted_task_type="analysis")
    orchestrator.register_agent(default_agent)
    orchestrator.register_agent(analyst_agent)

    await orchestrator.execute_task("task-3", "analyze me", task_type="default")
    assert analyst_agent.last_task is not None
    assert default_agent.last_task is None


@pytest.mark.asyncio
async def test_pre_hook_additional_steps_appended_to_prompt():
    hooks = HookSystem()

    def add_steps(task: dict) -> dict:
        updated = dict(task)
        updated["additional_steps"] = ["step one", "step two"]
        return updated

    hooks.register_hook("pre_task_execution", add_steps, priority=70)

    orchestrator = TaskOrchestrator(
        communication=CommunicationLayer(),
        plugin_hook_system=hooks,
    )
    agent = _EchoAgent(name="default_agent", accepted_task_type="default")
    orchestrator.register_agent(agent)

    await orchestrator.execute_task("task-4", "payload", task_type="default")
    assert agent.last_task is not None
    assert "Дополнительные шаги от плагинов" in agent.last_task["prompt"]
    assert "step one" in agent.last_task["prompt"]
