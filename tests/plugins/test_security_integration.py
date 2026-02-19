"""Security integration tests for loader, sandbox and monitor."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from vagus.plugins.core.models import LoadedPlugin, PluginLifecycleState, PluginManifest, PluginState
from vagus.plugins.loader import SecurePluginLoader
from vagus.plugins.monitoring import PluginMonitor
from vagus.plugins.registry import PluginRegistry
from vagus.plugins.sandbox import SandboxEngine, SandboxPolicy, SecurityViolationError


def _register_runtime_plugin(registry: PluginRegistry, plugin_name: str) -> LoadedPlugin:
    manifest = PluginManifest(
        name=plugin_name,
        version="1.0.0",
        author="Tests",
        description="Integration plugin",
        dependencies=[],
        python_version=">=3.10",
        vagus_version=">=0.1.0",
        entry_point="plugin:Entry",
        hooks=[],
        permissions=[],
    )
    loaded = LoadedPlugin(
        manifest=manifest,
        state=PluginState(state=PluginLifecycleState.ENABLED),
    )
    registry.register(loaded)
    return loaded


@pytest.mark.asyncio
async def test_security_integration_violation_disables_plugin():
    registry = PluginRegistry()
    registry.clear()
    plugin = _register_runtime_plugin(registry, "integration_plugin")
    monitor = PluginMonitor(registry=registry, security_violation_threshold=1)
    engine = SandboxEngine(policy=SandboxPolicy(timeout_seconds=5))

    def forbidden() -> None:
        subprocess.run(["echo", "test"], check=False)

    with pytest.raises(SecurityViolationError):
        await engine.execute_async(plugin, forbidden)

    monitor.record_security_violation(plugin.name, "process creation blocked")
    assert registry.get_plugin(plugin.name).state.state == PluginLifecycleState.DISABLED


@pytest.mark.asyncio
async def test_security_integration_secure_loader_and_sandbox(tmp_path: Path):
    plugin_dir = tmp_path / "plugin_secure_flow"
    plugin_dir.mkdir()
    allowed_dir = tmp_path / "allowed_data"
    allowed_dir.mkdir()
    target_file = allowed_dir / "data.txt"
    target_file.write_text("safe", encoding="utf-8")

    manifest = {
        "name": "plugin_secure_flow",
        "version": "1.0.0",
        "author": "Tests",
        "description": "Secure flow plugin",
        "dependencies": [],
        "python_version": ">=3.10",
        "vagus_version": ">=0.1.0",
        "entry_point": "plugin:Entry",
        "hooks": [],
        "permissions": [],
        "runtime_permissions": {
            "level": "READ",
            "filesystem": {"read": [str(allowed_dir)], "write": []},
            "network": [],
            "environment_variables": [],
            "max_memory_mb": 128,
            "max_execution_time_seconds": 5
        }
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "plugin.py").write_text(
        "class Entry:\n"
        "    def read_file(self, path):\n"
        "        with open(path, 'r', encoding='utf-8') as fh:\n"
        "            return fh.read()\n",
        encoding="utf-8",
    )

    loader = SecurePluginLoader(quarantine_dir=tmp_path / "quarantine")
    loaded = loader.load(plugin_dir)
    entry = loaded.entry_point()

    engine = SandboxEngine(
        policy=SandboxPolicy(
            timeout_seconds=5,
            filesystem_whitelist=[str(allowed_dir)],
            network_whitelist=[],
        )
    )
    result = await engine.execute_async(
        loaded,
        entry.read_file,
        str(target_file),
    )
    assert result == "safe"
