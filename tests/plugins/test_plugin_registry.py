"""Tests for plugin registry."""

from __future__ import annotations

import pytest

from vagus.plugins.core.models import (
    HookDefinition,
    LoadedPlugin,
    PluginLifecycleState,
    PluginManifest,
    PluginState,
)
from vagus.plugins.registry import PluginRegistry


@pytest.fixture()
def registry() -> PluginRegistry:
    reg = PluginRegistry()
    reg.clear()
    yield reg
    reg.clear()


def _create_plugin(name: str, state: PluginLifecycleState, hook_priority: int = 50) -> LoadedPlugin:
    manifest = PluginManifest(
        name=name,
        version="1.0.0",
        author="Tests",
        description=f"{name} test plugin",
        dependencies=[],
        python_version=">=3.10",
        vagus_version=">=0.1.0",
        entry_point="plugin:Demo",
        hooks=[
            HookDefinition(
                name="pre_task_execution",
                priority=hook_priority,
                callback="Demo.pre_task_execution",
                is_async=False,
            )
        ],
        permissions=[],
    )
    return LoadedPlugin(
        manifest=manifest,
        state=PluginState(state=state),
    )


def test_register_get_unregister_plugin(registry: PluginRegistry):
    plugin = _create_plugin("plugin_a", PluginLifecycleState.LOADED)
    registry.register(plugin)

    fetched = registry.get_plugin("plugin_a")
    assert fetched is not None
    assert fetched.name == "plugin_a"

    assert registry.unregister("plugin_a") is True
    assert registry.get_plugin("plugin_a") is None


def test_list_plugins_with_state_filter(registry: PluginRegistry):
    registry.register(_create_plugin("plugin_enabled", PluginLifecycleState.ENABLED))
    registry.register(_create_plugin("plugin_disabled", PluginLifecycleState.DISABLED))

    enabled_plugins = registry.list_plugins(state=PluginLifecycleState.ENABLED)
    assert [item.name for item in enabled_plugins] == ["plugin_enabled"]

    disabled_plugins = registry.list_plugins(state="DISABLED")
    assert [item.name for item in disabled_plugins] == ["plugin_disabled"]


def test_get_hooks_returns_sorted_by_priority(registry: PluginRegistry):
    registry.register(_create_plugin("plugin_low", PluginLifecycleState.ENABLED, hook_priority=10))
    registry.register(_create_plugin("plugin_high", PluginLifecycleState.ENABLED, hook_priority=90))

    hooks = registry.get_hooks("pre_task_execution")
    assert [hook.priority for hook in hooks] == [90, 10]
