"""Tests for plugin hot-reload manager."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from vagus.plugins.hooks import HookSystem
from vagus.plugins.hot_reload import HotReloadConfig, HotReloadManager
from vagus.plugins.loader import LocalLoader
from vagus.plugins.registry import PluginRegistry


def _write_hot_plugin(
    plugin_dir: Path,
    *,
    plugin_name: str,
    module_name: str,
    version_label: str,
) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": plugin_name,
        "version": "1.0.0",
        "author": "tests",
        "description": "hot reload plugin",
        "dependencies": [],
        "python_version": ">=3.10",
        "vagus_version": ">=0.1.0",
        "entry_point": f"{module_name}:Plugin",
        "hooks": [
            {
                "name": "on_message_received",
                "priority": 50,
                "callback": "Plugin.on_message_received",
                "is_async": False,
            }
        ],
        "permissions": [],
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / f"{module_name}.py").write_text(
        "class Plugin:\n"
        "    def on_message_received(self, message):\n"
        "        result = dict(message)\n"
        f"        result['version'] = '{version_label}'\n"
        "        return result\n",
        encoding="utf-8",
    )


@pytest.fixture()
def setup_runtime() -> tuple[PluginRegistry, HookSystem, LocalLoader]:
    registry = PluginRegistry()
    registry.clear()
    hook_system = HookSystem()
    loader = LocalLoader()
    yield registry, hook_system, loader
    registry.clear()
    hook_system.clear()


@pytest.mark.asyncio
async def test_hot_reload_manager_reloads_plugin_without_downtime(
    tmp_path: Path,
    setup_runtime,
):
    registry, hook_system, loader = setup_runtime
    plugin_dir = tmp_path / "hot_plugin"
    _write_hot_plugin(
        plugin_dir,
        plugin_name="hot_plugin",
        module_name="hot_entry_alpha",
        version_label="v1",
    )

    plugin = loader.load(plugin_dir)
    registry.register(plugin)
    manager = HotReloadManager(
        registry=registry,
        loader=loader,
        hook_system=hook_system,
        config=HotReloadConfig(enabled=True, debounce_ms=10),
    )
    manager.register_plugin(plugin)

    before = await hook_system.on_message_received({"text": "hello"})
    assert before["version"] == "v1"

    _write_hot_plugin(
        plugin_dir,
        plugin_name="hot_plugin",
        module_name="hot_entry_alpha",
        version_label="v2",
    )
    assert manager.reload_plugin("hot_plugin") is True

    after = await hook_system.on_message_received({"text": "hello"})
    assert after["version"] == "v2"


def test_hot_reload_manager_debounce(tmp_path: Path, setup_runtime, monkeypatch: pytest.MonkeyPatch):
    registry, hook_system, loader = setup_runtime
    plugin_dir = tmp_path / "debounce_plugin"
    _write_hot_plugin(
        plugin_dir,
        plugin_name="debounce_plugin",
        module_name="hot_entry_beta",
        version_label="v1",
    )
    plugin = loader.load(plugin_dir)
    registry.register(plugin)

    manager = HotReloadManager(
        registry=registry,
        loader=loader,
        hook_system=hook_system,
        config=HotReloadConfig(enabled=True, debounce_ms=1000),
    )

    calls: list[str] = []
    monkeypatch.setattr(manager, "reload_plugin", lambda name: calls.append(name) or True)

    target_file = plugin_dir / "hot_entry_beta.py"
    assert manager.on_file_changed(target_file) is True
    assert manager.on_file_changed(target_file) is False
    assert calls == ["debounce_plugin"]


def test_hot_reload_manager_ignores_unrelated_paths(tmp_path: Path, setup_runtime):
    registry, hook_system, loader = setup_runtime
    plugin_dir = tmp_path / "plugin_related"
    _write_hot_plugin(
        plugin_dir,
        plugin_name="plugin_related",
        module_name="hot_entry_gamma",
        version_label="v1",
    )
    plugin = loader.load(plugin_dir)
    registry.register(plugin)
    manager = HotReloadManager(registry=registry, loader=loader, hook_system=hook_system)

    unrelated = tmp_path / "other" / "file.py"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("print('x')", encoding="utf-8")
    assert manager.on_file_changed(unrelated) is False


def test_hot_reload_register_plugin_binds_hooks(tmp_path: Path, setup_runtime):
    registry, hook_system, loader = setup_runtime
    plugin_dir = tmp_path / "bind_plugin"
    _write_hot_plugin(
        plugin_dir,
        plugin_name="bind_plugin",
        module_name="hot_entry_delta",
        version_label="v1",
    )
    plugin = loader.load(plugin_dir)
    registry.register(plugin)

    manager = HotReloadManager(registry=registry, loader=loader, hook_system=hook_system)
    manager.register_plugin(plugin)

    hooks = hook_system.get_hooks("on_message_received")
    assert hooks
    assert len(hooks) == 1


def test_hot_reload_start_returns_false_when_disabled(setup_runtime):
    registry, hook_system, loader = setup_runtime
    manager = HotReloadManager(
        registry=registry,
        loader=loader,
        hook_system=hook_system,
        config=HotReloadConfig(enabled=False),
    )
    assert manager.start() is False
    assert manager.is_running is False
