"""Hot-reload manager for runtime plugin updates."""

from __future__ import annotations

import importlib
import inspect
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from ..core.models import LoadedPlugin, PluginLifecycleState
from ..hooks import HookSystem
from ..loader import LocalLoader
from ..registry import PluginRegistry

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    WATCHDOG_AVAILABLE = False
    FileSystemEventHandler = object  # type: ignore[assignment]
    Observer = None  # type: ignore[assignment]


@dataclass
class HotReloadConfig:
    """Configuration for plugin hot-reload system."""

    enabled: bool = True
    watch_directories: list[str] = field(default_factory=lambda: ["./plugins", "~/.vagus/plugins"])
    debounce_ms: int = 500


class HotReloadManager:
    """Monitors plugin files and reloads plugins on change."""

    def __init__(
        self,
        *,
        registry: Optional[PluginRegistry] = None,
        loader: Optional[LocalLoader] = None,
        hook_system: Optional[HookSystem] = None,
        config: Optional[HotReloadConfig] = None,
    ) -> None:
        self.registry = registry or PluginRegistry()
        self.loader = loader or LocalLoader()
        self.hook_system = hook_system or HookSystem()
        self.config = config or HotReloadConfig()

        self._observer = None
        self._running = False
        self._lock = threading.RLock()
        self._last_reload_at: dict[str, float] = {}
        self._plugin_hook_bindings: dict[str, list[tuple[str, Callable[..., Any]]]] = {}
        self._event_log: deque[dict[str, Any]] = deque(maxlen=2000)
        self._reload_history: dict[str, deque[dict[str, Any]]] = {}
        self._event_listeners: list[Callable[[dict[str, Any]], None]] = []

    def start(self) -> bool:
        """Start file watching if enabled and watchdog is available."""
        if not self.config.enabled:
            self._emit_event(
                "hot_reload_disabled",
                success=False,
                details={"reason": "hot_reload_disabled_in_config"},
            )
            return False
        if not WATCHDOG_AVAILABLE:
            self._emit_event(
                "watchdog_unavailable",
                success=False,
                details={"reason": "watchdog_not_installed"},
            )
            return False
        if self._running:
            self._emit_event("hot_reload_already_running", success=True)
            return True

        observer = Observer()
        handler = _PluginFileChangeHandler(self)
        for directory in self._normalized_watch_directories():
            if not directory.exists():
                continue
            observer.schedule(handler, str(directory), recursive=True)
        observer.start()
        self._observer = observer
        self._running = True
        self._emit_event(
            "hot_reload_started",
            success=True,
            details={
                "watch_directories": [str(path) for path in self._normalized_watch_directories()],
                "debounce_ms": int(self.config.debounce_ms),
            },
        )
        return True

    def stop(self) -> None:
        """Stop file watching."""
        if self._observer is None:
            self._running = False
            self._emit_event("hot_reload_stopped", success=True, details={"observer": "none"})
            return
        self._observer.stop()
        self._observer.join(timeout=5)
        self._observer = None
        self._running = False
        self._emit_event("hot_reload_stopped", success=True)

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def events_total(self) -> int:
        return len(self._event_log)

    def get_logs(self, *, limit: int = 100) -> list[dict[str, Any]]:
        max_items = max(1, int(limit))
        with self._lock:
            return list(self._event_log)[-max_items:]

    def get_reload_history(self, plugin_name: str, *, limit: int = 100) -> list[dict[str, Any]]:
        max_items = max(1, int(limit))
        with self._lock:
            history = self._reload_history.get(plugin_name)
            if history is None:
                return []
            return list(history)[-max_items:]

    def add_event_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._event_listeners.append(callback)

    def remove_event_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._event_listeners = [listener for listener in self._event_listeners if listener != callback]

    def on_file_changed(self, file_path: str | Path) -> bool:
        """Handle plugin file changes and trigger debounced reload."""
        changed_path = Path(file_path).expanduser().resolve()
        plugin = self._find_plugin_by_changed_path(changed_path)
        if plugin is None:
            self._emit_event(
                "file_change_ignored",
                success=False,
                details={"path": str(changed_path), "reason": "no_matching_plugin"},
            )
            return False

        now = time.monotonic()
        debounce_seconds = max(0.0, float(self.config.debounce_ms) / 1000.0)
        last_reload = self._last_reload_at.get(plugin.name, 0.0)
        if now - last_reload < debounce_seconds:
            self._emit_event(
                "file_change_debounced",
                plugin_name=plugin.name,
                success=False,
                details={"path": str(changed_path), "debounce_ms": int(self.config.debounce_ms)},
            )
            return False

        self._emit_event(
            "file_change_detected",
            plugin_name=plugin.name,
            success=True,
            details={"path": str(changed_path)},
        )
        reloaded = self.reload_plugin(plugin.name)
        self._emit_event(
            "file_change_reload",
            plugin_name=plugin.name,
            success=reloaded,
            details={"path": str(changed_path)},
        )
        if reloaded:
            self._last_reload_at[plugin.name] = now
        return reloaded

    def register_plugin(self, plugin: LoadedPlugin) -> None:
        """Register plugin hooks for managed hot-reload."""
        bindings = self._build_hook_bindings(plugin)
        for hook_name, callback, priority, is_async in bindings:
            self.hook_system.register_hook(
                hook_name=hook_name,
                callback=callback,
                priority=priority,
                is_async=is_async,
            )
        self._plugin_hook_bindings[plugin.name] = [(item[0], item[1]) for item in bindings]
        self._emit_event(
            "plugin_registered_for_hot_reload",
            plugin_name=plugin.name,
            success=True,
            details={"hooks": len(bindings)},
        )

    def reload_plugin(self, plugin_name: str) -> bool:
        """Gracefully reload plugin: load new, switch hooks, unload old."""
        with self._lock:
            current = self.registry.get_plugin(plugin_name)
            if current is None or not current.source:
                self._emit_event(
                    "plugin_reload_failed",
                    plugin_name=plugin_name,
                    success=False,
                    details={"reason": "plugin_not_found_or_source_missing"},
                )
                return False

            try:
                module_name = current.manifest.entry_point.partition(":")[0]
                if module_name:
                    sys.modules.pop(module_name, None)
                importlib.invalidate_caches()
                reloaded = self.loader.load(current.source)
                new_bindings = self._build_hook_bindings(reloaded)
            except Exception as exc:  # pragma: no cover - defensive branch
                current.state.state = PluginLifecycleState.ERROR
                current.state.error_message = str(exc)
                self._emit_event(
                    "plugin_reload_failed",
                    plugin_name=plugin_name,
                    success=False,
                    details={"reason": str(exc)},
                )
                return False

            registered_new: list[tuple[str, Callable[..., Any]]] = []
            try:
                # Register new hooks first (graceful no-downtime switch).
                for hook_name, callback, priority, is_async in new_bindings:
                    self.hook_system.register_hook(
                        hook_name=hook_name,
                        callback=callback,
                        priority=priority,
                        is_async=is_async,
                    )
                    registered_new.append((hook_name, callback))

                # Unregister old hooks only after new hooks are active.
                for old_hook_name, old_callback in self._plugin_hook_bindings.get(plugin_name, []):
                    self.hook_system.unregister_hook(old_hook_name, old_callback)

                # Replace plugin in registry.
                reloaded.state.state = PluginLifecycleState.ENABLED
                self.registry.register(reloaded)
                self._plugin_hook_bindings[plugin_name] = registered_new
                self._emit_event(
                    "plugin_reloaded",
                    plugin_name=plugin_name,
                    success=True,
                    details={"source": str(current.source)},
                )
                return True
            except Exception as exc:  # pragma: no cover - defensive rollback
                for hook_name, callback in registered_new:
                    self.hook_system.unregister_hook(hook_name, callback)
                current.state.state = PluginLifecycleState.ERROR
                current.state.error_message = str(exc)
                self._emit_event(
                    "plugin_reload_failed",
                    plugin_name=plugin_name,
                    success=False,
                    details={"reason": str(exc)},
                )
                return False

    def _build_hook_bindings(
        self,
        plugin: LoadedPlugin,
    ) -> list[tuple[str, Callable[..., Any], int, bool]]:
        target = self._build_runtime_target(plugin)
        bindings: list[tuple[str, Callable[..., Any], int, bool]] = []
        for hook in plugin.manifest.hooks:
            callback = self._resolve_hook_callback(target, hook.callback)
            bindings.append((hook.name, callback, hook.priority, hook.is_async))
        return bindings

    def _build_runtime_target(self, plugin: LoadedPlugin) -> Any:
        entry_point = plugin.entry_point
        if inspect.isclass(entry_point):
            return entry_point()
        if callable(entry_point) and not inspect.ismodule(entry_point):
            # For factory-style entry points returning plugin instances.
            try:
                result = entry_point()
                if result is not None:
                    return result
            except TypeError:
                pass
        return plugin.module or entry_point

    def _resolve_hook_callback(self, target: Any, callback_ref: Any) -> Callable[..., Any]:
        if callable(callback_ref):
            return callback_ref
        callback_name = str(callback_ref).rsplit(".", maxsplit=1)[-1]
        if hasattr(target, callback_name):
            callback = getattr(target, callback_name)
            if callable(callback):
                return callback
        raise AttributeError(f"Cannot resolve hook callback '{callback_ref}'")

    def _find_plugin_by_changed_path(self, changed_path: Path) -> Optional[LoadedPlugin]:
        for plugin in self.registry.list_plugins():
            if not plugin.source:
                continue
            source_root = Path(plugin.source).expanduser().resolve()
            if changed_path == source_root or changed_path.is_relative_to(source_root):
                return plugin
        return None

    def _normalized_watch_directories(self) -> list[Path]:
        return [Path(item).expanduser().resolve() for item in self.config.watch_directories]

    def _emit_event(
        self,
        event_type: str,
        *,
        plugin_name: Optional[str] = None,
        success: Optional[bool] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "plugin_name": plugin_name,
            "success": success,
            "details": details or {},
        }
        with self._lock:
            self._event_log.append(event)
            if plugin_name:
                history = self._reload_history.setdefault(plugin_name, deque(maxlen=500))
                history.append(event)
            listeners = list(self._event_listeners)
        for listener in listeners:
            try:
                listener(dict(event))
            except Exception:
                # Listener errors must never break hot-reload.
                continue
        return event


class _PluginFileChangeHandler(FileSystemEventHandler):
    """Watchdog event handler that routes file updates to manager."""

    def __init__(self, manager: HotReloadManager) -> None:
        self.manager = manager

    def on_modified(self, event):  # noqa: ANN001 - watchdog signature
        if getattr(event, "is_directory", False):
            return
        self.manager.on_file_changed(getattr(event, "src_path", ""))

    def on_created(self, event):  # noqa: ANN001 - watchdog signature
        if getattr(event, "is_directory", False):
            return
        self.manager.on_file_changed(getattr(event, "src_path", ""))
