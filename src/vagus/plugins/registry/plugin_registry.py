"""Thread-safe singleton registry for plugin runtime objects."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Optional

from ..core.models import (
    HookDefinition,
    LoadedPlugin,
    PluginLifecycleState,
    PluginManifest,
    PluginState,
)


class PluginRegistry:
    """Central registry of all loaded plugins."""

    _instance: Optional["PluginRegistry"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "PluginRegistry":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False  # type: ignore[attr-defined]
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._plugins: dict[str, LoadedPlugin] = {}
        self._lock = threading.RLock()
        self._initialized = True

    def register(self, plugin: LoadedPlugin | PluginManifest | dict[str, Any]) -> LoadedPlugin:
        """Register plugin in the runtime registry."""
        normalized = self._normalize_plugin(plugin)
        with self._lock:
            self._plugins[normalized.name] = normalized
        return normalized

    def unregister(self, plugin_name: str) -> bool:
        """Remove plugin from registry."""
        with self._lock:
            removed = self._plugins.pop(plugin_name, None)
        return removed is not None

    def get_plugin(self, name: str) -> Optional[LoadedPlugin]:
        """Get plugin by name."""
        with self._lock:
            return self._plugins.get(name)

    def list_plugins(self, state: Optional[PluginLifecycleState | str] = None) -> list[LoadedPlugin]:
        """List all plugins, optionally filtered by lifecycle state."""
        with self._lock:
            plugins = list(self._plugins.values())

        if state is None:
            return plugins

        desired_state = self._normalize_state(state)
        return [plugin for plugin in plugins if plugin.state.state == desired_state]

    def get_hooks(self, hook_name: str) -> list[HookDefinition]:
        """Get all hooks by name sorted by priority."""
        with self._lock:
            plugins = list(self._plugins.values())

        hooks: list[HookDefinition] = []
        for plugin in plugins:
            for hook in plugin.hooks:
                if hook.name == hook_name:
                    hooks.append(hook)

        hooks.sort(key=lambda item: item.priority, reverse=True)
        return hooks

    def clear(self) -> None:
        """Clear registry state (useful for tests)."""
        with self._lock:
            self._plugins.clear()

    def _normalize_plugin(self, plugin: LoadedPlugin | PluginManifest | dict[str, Any]) -> LoadedPlugin:
        if isinstance(plugin, LoadedPlugin):
            return plugin

        if isinstance(plugin, PluginManifest):
            return LoadedPlugin(
                manifest=plugin,
                state=PluginState(
                    state=PluginLifecycleState.LOADED,
                    load_time=datetime.now(timezone.utc),
                ),
            )

        if isinstance(plugin, dict):
            if "manifest" in plugin:
                return LoadedPlugin.model_validate(plugin)
            return LoadedPlugin(manifest=PluginManifest.model_validate(plugin))

        raise TypeError("Plugin must be LoadedPlugin, PluginManifest, or dict payload")

    @staticmethod
    def _normalize_state(state: PluginLifecycleState | str) -> PluginLifecycleState:
        if isinstance(state, PluginLifecycleState):
            return state

        state_value = str(state).strip().upper()
        try:
            return PluginLifecycleState(state_value)
        except ValueError as exc:
            raise ValueError(
                f"Unknown plugin state '{state}'. Expected one of: {[s.value for s in PluginLifecycleState]}"
            ) from exc
