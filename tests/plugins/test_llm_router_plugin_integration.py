"""Integration tests for plugin hooks in LLMRouter."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict

import pytest

from vagus.layer1.providers.base_provider import LLMProvider
from vagus.layer1.router.llm_router import LLMRouter
from vagus.plugins.core.models import LoadedPlugin, PluginManifest
from vagus.plugins.hooks import HookSystem
from vagus.plugins.registry import PluginRegistry


class _EchoProvider(LLMProvider):
    async def request(
        self,
        prompt: str,
        stream: bool = False,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if kwargs.get("raise_error"):
            raise RuntimeError("provider boom")
        yield {"content": prompt, "done": True}

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return 0.0


def _build_router(*, hooks: HookSystem | None = None, registry: PluginRegistry | None = None) -> LLMRouter:
    router = LLMRouter(
        enable_cache=False,
        enable_budgeting=False,
        enable_monitoring=False,
        plugin_hook_system=hooks,
        plugin_registry=registry,
    )
    router._providers = {  # pylint: disable=protected-access
        "dummy": _EchoProvider(name="dummy", model="demo", api_key="secret")
    }
    return router


@pytest.mark.asyncio
async def test_llm_router_pre_hook_modifies_prompt():
    hooks = HookSystem()

    def pre_hook(context: dict) -> dict:
        updated = dict(context)
        updated["prompt"] = f"{updated['prompt']} [plugin]"
        return updated

    hooks.register_hook("pre_llm_call", pre_hook, priority=80)
    router = _build_router(hooks=hooks)

    chunks = [chunk async for chunk in router.route_request("hello", stream=True)]
    assert chunks
    assert chunks[-1]["content"].endswith("[plugin]")


@pytest.mark.asyncio
async def test_llm_router_post_hook_transforms_response():
    hooks = HookSystem()

    def post_hook(_: dict, response: dict) -> dict:
        return {"content": "post-processed", "stream": True}

    hooks.register_hook("post_llm_call", post_hook, priority=80)
    router = _build_router(hooks=hooks)

    chunks = [chunk async for chunk in router.route_request("hello", stream=True)]
    assert chunks[-1]["content"] == "post-processed"


@pytest.mark.asyncio
async def test_llm_router_error_hook_called_on_failure():
    hooks = HookSystem()
    captured: list[str] = []

    def error_hook(context: dict, error: Exception) -> None:
        captured.append(f"{context.get('prompt')}:{error}")

    hooks.register_hook("on_llm_error", error_hook, priority=80)
    router = _build_router(hooks=hooks)

    with pytest.raises(RuntimeError):
        async for _ in router.route_request("oops", stream=True, raise_error=True):
            pass

    assert captured and captured[0].startswith("oops:")


@pytest.mark.asyncio
async def test_llm_router_registers_custom_provider_from_plugin_registry():
    class CustomProvider(LLMProvider):
        async def request(self, prompt: str, stream: bool = False, **kwargs):
            yield {"content": "custom", "done": True}

        def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
            return 0.0

    class PluginRuntime:
        llm_providers = {"custom": CustomProvider}

    plugin_registry = PluginRegistry()
    plugin_registry.clear()
    plugin_registry.register(
        LoadedPlugin(
            manifest=PluginManifest(
                name="llm_plugin",
                version="1.0.0",
                author="tests",
                description="llm plugin",
                dependencies=[],
                python_version=">=3.10",
                vagus_version=">=0.1.0",
                entry_point="plugin:PluginRuntime",
                hooks=[],
                permissions=[],
            ),
            entry_point=PluginRuntime,
        )
    )

    router = _build_router(registry=plugin_registry)
    router._register_plugin_providers()  # pylint: disable=protected-access
    assert router.provider_factory.registry.has("custom") is True


@pytest.mark.asyncio
async def test_llm_router_initializes_custom_provider_from_config():
    class CustomProvider(LLMProvider):
        async def request(self, prompt: str, stream: bool = False, **kwargs):
            yield {"content": "custom", "done": True}

        def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
            return 0.0

    class PluginRuntime:
        llm_providers = {"customcfg": CustomProvider}

    plugin_registry = PluginRegistry()
    plugin_registry.clear()
    plugin_registry.register(
        LoadedPlugin(
            manifest=PluginManifest(
                name="llm_plugin_cfg",
                version="1.0.0",
                author="tests",
                description="llm plugin cfg",
                dependencies=[],
                python_version=">=3.10",
                vagus_version=">=0.1.0",
                entry_point="plugin:PluginRuntime",
                hooks=[],
                permissions=[],
            ),
            entry_point=PluginRuntime,
        )
    )

    router = LLMRouter(
        enable_cache=False,
        enable_budgeting=False,
        enable_monitoring=False,
        plugin_registry=plugin_registry,
    )
    await router.initialize(
        providers_config={
            "customcfg": {
                "enabled": True,
                "models": ["custom-model"],
                "api_key": "secret",
                "timeout": 5,
            }
        }
    )
    assert "customcfg" in router._providers  # pylint: disable=protected-access
