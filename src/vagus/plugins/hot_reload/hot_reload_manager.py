"""Hot-reload manager for runtime plugin updates."""

from __future__ import annotations

import importlib
import inspect
import sys
import threading
import time
from dataclasses import dataclass, field
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

    def start(self) -> bool:
        """Start file watching if enabled and watchdog is available."""
        if not self.config.enabled:
            return False
        if not WATCHDOG_AVAILABLE:
            return False
        if self._running:
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
        return True

    def stop(self) -> None:
        """Stop file watching."""
        if self._observer is None:
            self._running = False
            return
        self._observer.stop()
        self._observer.join(timeout=5)
        self._observer = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def on_file_changed(self, file_path: str | Path) -> bool:
        """Handle plugin file changes and trigger debounced reload."""
        changed_path = Path(file_path).expanduser().resolve()
        plugin = self._find_plugin_by_changed_path(changed_path)
        if plugin is None:
            return False

        now = time.monotonic()
        debounce_seconds = max(0.0, float(self.config.debounce_ms) / 1000.0)
        last_reload = self._last_reload_at.get(plugin.name, 0.0)
        if now - last_reload < debounce_seconds:
            return False

        reloaded = self.reload_plugin(plugin.name)
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

    def reload_plugin(self, plugin_name: str) -> bool:
        """Gracefully reload plugin: load new, switch hooks, unload old."""
        with self._lock:
            current = self.registry.get_plugin(plugin_name)
            if current is None or not current.source:
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
                return True
            except Exception as exc:  # pragma: no cover - defensive rollback
                for hook_name, callback in registered_new:
                    self.hook_system.unregister_hook(hook_name, callback)
                current.state.state = PluginLifecycleState.ERROR
                current.state.error_message = str(exc)
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
