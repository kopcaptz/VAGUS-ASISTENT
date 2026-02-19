"""End-to-end integration tests for full integration demo plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from vagus.layer1.providers.base_provider import LLMProvider
from vagus.layer1.router.llm_router import LLMRouter
from vagus.layer2 import CommunicationLayer, TaskOrchestrator
from vagus.layer2.agents.base_agent import BaseAgent
from vagus.plugins.hooks import HookSystem
from vagus.plugins.integration import (
    CLIPluginIntegration,
    DashboardPluginIntegration,
    TelegramPluginIntegration,
)
from vagus.plugins.loader import LocalLoader


class _PromptEchoProvider(LLMProvider):
    async def request(self, prompt: str, stream: bool = False, **kwargs):
        yield {"content": prompt, "done": True}

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return 0.0


class _LLMAgent(BaseAgent):
    def __init__(self, llm_router):
        super().__init__(name="llm_agent", llm_router=llm_router)

    def can_handle(self, task_type: str) -> bool:
        return True

    async def process(self, task: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        chunks = [chunk async for chunk in self.llm_router.route_request(task["prompt"], stream=True)]
        return {"success": True, "content": "".join(chunk.get("content", "") for chunk in chunks)}


def _load_demo_runtime():
    plugin_path = Path(__file__).resolve().parents[2] / "examples" / "plugins" / "full_integration_demo"
    plugin = LocalLoader().load(str(plugin_path))
    runtime = plugin.entry_point() if isinstance(plugin.entry_point, type) else plugin.entry_point
    return plugin, runtime


def test_full_integration_demo_discovery_across_surfaces():
    plugin, runtime = _load_demo_runtime()

    dashboard = DashboardPluginIntegration()
    cli = CLIPluginIntegration()
    telegram = TelegramPluginIntegration()

    dashboard.discover_from_plugin(plugin.name, runtime)
    cli.discover_from_plugin(plugin.name, runtime)
    telegram.discover_from_plugin(plugin.name, runtime)

    assert dashboard.list_pages()
    assert dashboard.list_widgets(target_page="performance")
    assert plugin.name in cli._plugin_commands  # pylint: disable=protected-access
    assert telegram.get_inline_buttons()


@pytest.mark.asyncio
async def test_full_integration_demo_task_and_llm_hooks_work_together():
    _, runtime = _load_demo_runtime()
    orchestrator_hooks = HookSystem()
    llm_hooks = HookSystem()

    orchestrator_hooks.register_hook("pre_task_execution", runtime.pre_task_execution, priority=90)
    orchestrator_hooks.register_hook("post_task_execution", runtime.post_task_execution, priority=90)
    llm_hooks.register_hook("pre_llm_call", runtime.pre_llm_call, priority=90)

    router = LLMRouter(
        enable_cache=False,
        enable_budgeting=False,
        enable_monitoring=False,
        plugin_hook_system=llm_hooks,
    )
    router._providers = {  # pylint: disable=protected-access
        "echo": _PromptEchoProvider(name="echo", model="demo", api_key="secret")
    }

    orchestrator = TaskOrchestrator(
        communication=CommunicationLayer(),
        plugin_hook_system=orchestrator_hooks,
    )
    orchestrator.register_agent(_LLMAgent(router))

    result = await orchestrator.execute_task(
        "e2e-integration",
        "Original prompt",
        task_type="default",
        metadata={"trace": "x"},
    )
    assert result.get("plugin_note") == "processed by full_integration_demo"
    assert "[Plugin context: full integration demo]" in result.get("content", "")
    assert "Дополнительные шаги от плагинов" in result.get("content", "")
