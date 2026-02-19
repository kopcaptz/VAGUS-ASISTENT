"""Lifecycle management for plugin install/load/enable/run/disable/uninstall."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from ..core.models import LoadedPlugin, PluginLifecycleState
from ..loader import GitLoader, LocalLoader, PyPILoader
from ..monitoring import PluginMonitor
from ..registry import PluginRegistry


class PluginLifecycleStage(str, Enum):
    INSTALL = "INSTALL"
    LOAD = "LOAD"
    ENABLE = "ENABLE"
    RUN = "RUN"
    DISABLE = "DISABLE"
    UNINSTALL = "UNINSTALL"


@dataclass
class PluginLifecycleRecord:
    plugin_name: str
    stage: PluginLifecycleStage
    details: str = ""


class PluginLifecycleManager:
    """Manages full plugin lifecycle and basic recovery/upgrade flows."""

    def __init__(
        self,
        *,
        registry: Optional[PluginRegistry] = None,
        local_loader: Optional[LocalLoader] = None,
        git_loader: Optional[GitLoader] = None,
        pypi_loader: Optional[PyPILoader] = None,
        monitor: Optional[PluginMonitor] = None,
        migration_manager: Optional[Any] = None,
    ) -> None:
        self.registry = registry or PluginRegistry()
        self.local_loader = local_loader or LocalLoader()
        self.git_loader = git_loader or GitLoader(local_loader=self.local_loader)
        self.pypi_loader = pypi_loader or PyPILoader(local_loader=self.local_loader)
        self.monitor = monitor or PluginMonitor(registry=self.registry)
        self.migration_manager = migration_manager
        self._history: list[PluginLifecycleRecord] = []

    def install(self, source: str, *, source_type: str = "local", ref: Optional[str] = None) -> LoadedPlugin:
        self._record("<pending>", PluginLifecycleStage.INSTALL, f"source={source_type}:{source}")
        if source_type == "local":
            plugin = self.local_loader.load(source)
        elif source_type == "git":
            plugin = self.git_loader.load(source, ref=ref)
        elif source_type == "pypi":
            plugin = self.pypi_loader.load(source, version=ref)
        else:
            raise ValueError(f"Unsupported source_type '{source_type}'")

        self.registry.register(plugin)
        self._record(plugin.name, PluginLifecycleStage.LOAD, "Plugin loaded and registered")
        return plugin

    def load(self, plugin_path: str) -> LoadedPlugin:
        plugin = self.local_loader.load(plugin_path)
        self.registry.register(plugin)
        self._record(plugin.name, PluginLifecycleStage.LOAD, "Plugin loaded")
        return plugin

    def enable(self, plugin_name: str) -> LoadedPlugin:
        plugin = self._require_plugin(plugin_name)
        plugin.state.state = PluginLifecycleState.ENABLED
        plugin.state.error_message = None
        self._record(plugin_name, PluginLifecycleStage.ENABLE, "Plugin enabled")
        return plugin

    def disable(self, plugin_name: str, reason: str = "") -> LoadedPlugin:
        plugin = self._require_plugin(plugin_name)
        plugin.state.state = PluginLifecycleState.DISABLED
        if reason:
            plugin.state.error_message = reason
        self._record(plugin_name, PluginLifecycleStage.DISABLE, reason or "Plugin disabled")
        return plugin

    def uninstall(self, plugin_name: str) -> bool:
        removed = self.registry.unregister(plugin_name)
        if removed:
            self._record(plugin_name, PluginLifecycleStage.UNINSTALL, "Plugin uninstalled")
        return removed

    async def run(
        self,
        plugin_name: str,
        callback_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        plugin = self._require_plugin(plugin_name)
        if plugin.state.state != PluginLifecycleState.ENABLED:
            self.enable(plugin_name)

        callback = self._resolve_callback(plugin, callback_name)
        self._record(plugin_name, PluginLifecycleStage.RUN, f"callback={callback_name}")
        try:
            if inspect.iscoroutinefunction(callback):
                result = await callback(*args, **kwargs)
            else:
                result = callback(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
            return result
        except Exception as exc:
            plugin.state.state = PluginLifecycleState.ERROR
            plugin.state.error_message = str(exc)
            raise

    def health_check(self, plugin_name: str) -> str:
        plugin = self._require_plugin(plugin_name)
        status = self.monitor.evaluate_plugin(plugin_name, permissions=plugin.manifest.runtime_permissions)
        if status.value == "DISABLED":
            plugin.state.state = PluginLifecycleState.DISABLED
        return status.value

    def recover(self, plugin_name: str) -> bool:
        plugin = self._require_plugin(plugin_name)
        if plugin.state.state != PluginLifecycleState.ERROR:
            return False
        plugin.state.state = PluginLifecycleState.DISABLED
        plugin.state.error_message = None
        plugin.state.state = PluginLifecycleState.ENABLED
        self._record(plugin_name, PluginLifecycleStage.ENABLE, "Plugin recovered after crash")
        return True

    def upgrade(
        self,
        plugin_name: str,
        new_source: str,
        *,
        source_type: str = "local",
        target_version: Optional[str] = None,
    ) -> LoadedPlugin:
        current = self._require_plugin(plugin_name)
        old_version = current.manifest.version
        current_config = current.config.settings

        upgraded = self.install(new_source, source_type=source_type)
        if upgraded.name != plugin_name:
            self.registry.unregister(upgraded.name)
            raise RuntimeError(
                f"Upgrade source produced plugin '{upgraded.name}', expected '{plugin_name}'"
            )

        if self.migration_manager is not None and current_config:
            desired_version = target_version or upgraded.manifest.version
            migrated = self.migration_manager.migrate_config(
                plugin_name=plugin_name,
                current_version=old_version,
                target_version=desired_version,
                config=current_config,
            )
            upgraded.config.settings = migrated

        self.registry.register(upgraded)
        upgraded.state.state = PluginLifecycleState.ENABLED
        self._record(
            plugin_name,
            PluginLifecycleStage.ENABLE,
            f"Plugin upgraded {old_version} -> {upgraded.manifest.version}",
        )
        return upgraded

    def history(self, plugin_name: Optional[str] = None) -> list[PluginLifecycleRecord]:
        if plugin_name is None:
            return list(self._history)
        return [item for item in self._history if item.plugin_name == plugin_name]

    def _require_plugin(self, plugin_name: str) -> LoadedPlugin:
        plugin = self.registry.get_plugin(plugin_name)
        if plugin is None:
            raise KeyError(f"Plugin '{plugin_name}' is not registered")
        return plugin

    def _resolve_callback(self, plugin: LoadedPlugin, callback_name: str) -> Callable[..., Any]:
        entry = plugin.entry_point
        runtime = entry
        if inspect.isclass(entry):
            runtime = entry()
        if hasattr(runtime, callback_name):
            callback = getattr(runtime, callback_name)
            if callable(callback):
                return callback
        if plugin.module is not None and hasattr(plugin.module, callback_name):
            callback = getattr(plugin.module, callback_name)
            if callable(callback):
                return callback
        raise AttributeError(f"Callback '{callback_name}' not found in plugin '{plugin.name}'")

    def _record(self, plugin_name: str, stage: PluginLifecycleStage, details: str) -> None:
        self._history.append(PluginLifecycleRecord(plugin_name=plugin_name, stage=stage, details=details))
