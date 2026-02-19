"""Tests for plugin lifecycle management."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vagus.plugins.lifecycle import PluginLifecycleManager, PluginLifecycleStage
from vagus.plugins.migration import PluginMigrationManager
from vagus.plugins.registry import PluginRegistry
from vagus.plugins.core.models import PluginLifecycleState


def _write_plugin(plugin_dir: Path, *, name: str, version: str, marker: str) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": version,
        "author": "tests",
        "description": "lifecycle plugin",
        "dependencies": [],
        "python_version": ">=3.10",
        "vagus_version": ">=0.1.0",
        "entry_point": "plugin:Plugin",
        "hooks": [],
        "permissions": [],
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "plugin.py").write_text(
        "class Plugin:\n"
        "    def execute(self, value):\n"
        f"        return '{marker}:' + str(value)\n",
        encoding="utf-8",
    )


def test_plugin_lifecycle_install_enable_disable_uninstall(tmp_path: Path):
    registry = PluginRegistry()
    registry.clear()
    plugin_dir = tmp_path / "plugin_v1"
    _write_plugin(plugin_dir, name="life_plugin", version="1.0.0", marker="v1")

    manager = PluginLifecycleManager(registry=registry)
    loaded = manager.install(str(plugin_dir), source_type="local")
    assert loaded.name == "life_plugin"

    enabled = manager.enable("life_plugin")
    assert enabled.state.state.value == "ENABLED"

    disabled = manager.disable("life_plugin")
    assert disabled.state.state.value == "DISABLED"

    assert manager.uninstall("life_plugin") is True
    assert registry.get_plugin("life_plugin") is None


@pytest.mark.asyncio
async def test_plugin_lifecycle_run_callback(tmp_path: Path):
    registry = PluginRegistry()
    registry.clear()
    plugin_dir = tmp_path / "plugin_v1"
    _write_plugin(plugin_dir, name="run_plugin", version="1.0.0", marker="run")

    manager = PluginLifecycleManager(registry=registry)
    manager.install(str(plugin_dir), source_type="local")
    manager.enable("run_plugin")
    result = await manager.run("run_plugin", "execute", 42)
    assert result == "run:42"


def test_plugin_lifecycle_health_check(tmp_path: Path):
    registry = PluginRegistry()
    registry.clear()
    plugin_dir = tmp_path / "plugin_health"
    _write_plugin(plugin_dir, name="health_plugin", version="1.0.0", marker="health")

    manager = PluginLifecycleManager(registry=registry)
    manager.install(str(plugin_dir), source_type="local")
    manager.enable("health_plugin")
    health = manager.health_check("health_plugin")
    assert health in {"HEALTHY", "DEGRADED", "DISABLED"}


def test_plugin_lifecycle_recover_from_error(tmp_path: Path):
    registry = PluginRegistry()
    registry.clear()
    plugin_dir = tmp_path / "plugin_recover"
    _write_plugin(plugin_dir, name="recover_plugin", version="1.0.0", marker="rec")

    manager = PluginLifecycleManager(registry=registry)
    manager.install(str(plugin_dir), source_type="local")
    plugin = manager.enable("recover_plugin")
    plugin.state.state = PluginLifecycleState.ERROR
    plugin.state.error_message = "crash"

    assert manager.recover("recover_plugin") is True
    assert registry.get_plugin("recover_plugin").state.state.value == "ENABLED"


def test_plugin_lifecycle_upgrade_with_migration(tmp_path: Path):
    registry = PluginRegistry()
    registry.clear()
    v1_dir = tmp_path / "plugin_v1"
    v2_dir = tmp_path / "plugin_v2"
    _write_plugin(v1_dir, name="upgrade_plugin", version="1.0.0", marker="v1")
    _write_plugin(v2_dir, name="upgrade_plugin", version="1.1.0", marker="v2")

    migration_manager = PluginMigrationManager()
    migration_manager.register_migration(
        "upgrade_plugin",
        "1.0.0",
        "1.1.0",
        lambda cfg: {**cfg, "migrated": True},
    )

    manager = PluginLifecycleManager(
        registry=registry,
        migration_manager=migration_manager,
    )
    plugin = manager.install(str(v1_dir), source_type="local")
    plugin.config.settings = {"feature": "old"}

    upgraded = manager.upgrade(
        "upgrade_plugin",
        str(v2_dir),
        source_type="local",
        target_version="1.1.0",
    )
    assert upgraded.manifest.version == "1.1.0"
    assert upgraded.config.settings.get("migrated") is True
    stages = [record.stage for record in manager.history("upgrade_plugin")]
    assert PluginLifecycleStage.ENABLE in stages
