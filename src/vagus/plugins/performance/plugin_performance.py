"""Performance optimization helpers for plugin runtime execution."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from dataclasses import dataclass
from typing import Any, Optional

from ..loader import LocalLoader
from ..registry import PluginRegistry


@dataclass
class CachedPluginResult:
    value: Any
    expires_at: float
    created_at: float


class PluginPerformanceOptimizer:
    """Lazy loading, result caching and parallel execution utilities."""

    def __init__(
        self,
        *,
        registry: Optional[PluginRegistry] = None,
        loader: Optional[LocalLoader] = None,
        default_cache_ttl_seconds: int = 60,
    ) -> None:
        self.registry = registry or PluginRegistry()
        self.loader = loader or LocalLoader()
        self.default_cache_ttl_seconds = max(1, int(default_cache_ttl_seconds))
        self._lazy_sources: dict[str, str] = {}
        self._cache: dict[str, CachedPluginResult] = {}

    def register_lazy_plugin(self, plugin_name: str, plugin_path: str) -> None:
        self._lazy_sources[plugin_name] = plugin_path

    def get_plugin(self, plugin_name: str):
        plugin = self.registry.get_plugin(plugin_name)
        if plugin is not None:
            return plugin
        source = self._lazy_sources.get(plugin_name)
        if not source:
            raise KeyError(f"Plugin '{plugin_name}' is not loaded and has no lazy source")
        loaded = self.loader.load(source)
        self.registry.register(loaded)
        return loaded

    async def execute_with_cache(
        self,
        plugin_name: str,
        callback_name: str,
        *args: Any,
        cache_ttl_seconds: Optional[int] = None,
        **kwargs: Any,
    ) -> Any:
        ttl = self.default_cache_ttl_seconds if cache_ttl_seconds is None else max(1, int(cache_ttl_seconds))
        cache_key = self._build_cache_key(plugin_name, callback_name, args, kwargs)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        plugin = self.get_plugin(plugin_name)
        callback = self._resolve_callback(plugin, callback_name)
        if inspect.iscoroutinefunction(callback):
            result = await callback(*args, **kwargs)
        else:
            result = callback(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result

        self._cache_set(cache_key, result, ttl_seconds=ttl)
        return result

    async def execute_parallel(
        self,
        calls: list[dict[str, Any]],
        *,
        max_concurrency: int = 5,
    ) -> list[Any]:
        semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))

        async def _run(call: dict[str, Any]) -> Any:
            async with semaphore:
                return await self.execute_with_cache(
                    call["plugin_name"],
                    call["callback_name"],
                    *(call.get("args", []) or []),
                    **(call.get("kwargs", {}) or {}),
                )

        coroutines = [_run(call) for call in calls]
        return await asyncio.gather(*coroutines)

    def optimize_memory(self, *, max_cache_entries: int = 256) -> int:
        """Prunes oldest cache entries and returns current cache size."""
        if max_cache_entries < 1:
            max_cache_entries = 1

        now = time.time()
        expired_keys = [key for key, entry in self._cache.items() if entry.expires_at < now]
        for key in expired_keys:
            self._cache.pop(key, None)

        if len(self._cache) <= max_cache_entries:
            return len(self._cache)

        ordered = sorted(self._cache.items(), key=lambda item: item[1].created_at)
        for key, _ in ordered[: len(self._cache) - max_cache_entries]:
            self._cache.pop(key, None)
        return len(self._cache)

    def cache_size(self) -> int:
        return len(self._cache)

    def clear_cache(self) -> None:
        self._cache.clear()

    def _resolve_callback(self, plugin: Any, callback_name: str):
        entry = plugin.entry_point
        runtime = entry() if inspect.isclass(entry) else entry
        if runtime is not None and hasattr(runtime, callback_name):
            callback = getattr(runtime, callback_name)
            if callable(callback):
                return callback
        if plugin.module is not None and hasattr(plugin.module, callback_name):
            callback = getattr(plugin.module, callback_name)
            if callable(callback):
                return callback
        raise AttributeError(f"Callback '{callback_name}' not found in plugin '{plugin.name}'")

    def _cache_get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.time():
            self._cache.pop(key, None)
            return None
        return entry.value

    def _cache_set(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        now = time.time()
        self._cache[key] = CachedPluginResult(
            value=value,
            expires_at=now + max(1, int(ttl_seconds)),
            created_at=now,
        )

    @staticmethod
    def _build_cache_key(
        plugin_name: str,
        callback_name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> str:
        def _safe(value: Any) -> str:
            try:
                return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)
            except Exception:
                return repr(value)

        return (
            f"{plugin_name}:{callback_name}:"
            f"{_safe(list(args))}:{_safe(kwargs)}"
        )
