"""Tests for plugin health monitor."""

from __future__ import annotations

from vagus.plugins.core.models import (
    LoadedPlugin,
    PermissionLevel,
    PluginLifecycleState,
    PluginManifest,
    PluginPermissions,
    PluginState,
)
from vagus.plugins.monitoring import PluginHealthStatus, PluginMonitor
from vagus.plugins.registry import PluginRegistry


def _register_plugin(plugin_name: str) -> PluginRegistry:
    registry = PluginRegistry()
    registry.clear()
    manifest = PluginManifest(
        name=plugin_name,
        version="1.0.0",
        author="Tests",
        description="Monitored plugin",
        dependencies=[],
        python_version=">=3.10",
        vagus_version=">=0.1.0",
        entry_point="plugin:Entry",
        hooks=[],
        permissions=[],
    )
    registry.register(
        LoadedPlugin(
            manifest=manifest,
            state=PluginState(state=PluginLifecycleState.ENABLED),
        )
    )
    return registry


def test_plugin_monitor_records_metrics():
    registry = _register_plugin("metrics_plugin")
    monitor = PluginMonitor(registry=registry)

    monitor.record_execution(
        "metrics_plugin",
        execution_time_seconds=1.5,
        memory_usage_mb=128.0,
        failed=False,
    )
    metrics = monitor.get_metrics("metrics_plugin")
    assert metrics.executions == 1
    assert metrics.average_execution_time_seconds == 1.5
    assert metrics.max_memory_usage_mb == 128.0


def test_plugin_monitor_disables_on_high_error_rate():
    registry = _register_plugin("error_plugin")
    monitor = PluginMonitor(registry=registry, max_error_rate=0.4)

    for _ in range(3):
        monitor.record_execution(
            "error_plugin",
            execution_time_seconds=0.2,
            memory_usage_mb=32.0,
            failed=True,
            error_message="boom",
        )

    status = monitor.evaluate_plugin("error_plugin")
    plugin = registry.get_plugin("error_plugin")
    assert status == PluginHealthStatus.DISABLED
    assert plugin is not None
    assert plugin.state.state == PluginLifecycleState.DISABLED


def test_plugin_monitor_disables_on_memory_limit():
    registry = _register_plugin("memory_plugin")
    monitor = PluginMonitor(registry=registry)
    monitor.record_execution(
        "memory_plugin",
        execution_time_seconds=0.1,
        memory_usage_mb=700.0,
        failed=False,
    )
    permissions = PluginPermissions(
        level=PermissionLevel.READ,
        max_memory_mb=256,
        max_execution_time_seconds=30,
    )

    status = monitor.evaluate_plugin("memory_plugin", permissions=permissions)
    assert status == PluginHealthStatus.DISABLED


def test_plugin_monitor_security_violations_trigger_disable():
    registry = _register_plugin("security_plugin")
    monitor = PluginMonitor(registry=registry, security_violation_threshold=2)

    monitor.record_security_violation("security_plugin", "blocked network call")
    plugin = registry.get_plugin("security_plugin")
    assert plugin is not None
    assert plugin.state.state == PluginLifecycleState.ENABLED

    monitor.record_security_violation("security_plugin", "blocked process creation")
    assert registry.get_plugin("security_plugin").state.state == PluginLifecycleState.DISABLED
    assert monitor.get_alerts()
