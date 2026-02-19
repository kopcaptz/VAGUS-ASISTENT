"""HTTP client for Vagus plugin marketplace."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    HTTPX_AVAILABLE = False
    httpx = None  # type: ignore[assignment]


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


class MarketplaceClient:
    """Marketplace API client with caching and offline fallback."""

    def __init__(
        self,
        url: str = "https://plugins.vagus.ai",
        cache_ttl_hours: int = 24,
        *,
        offline_mode: bool = False,
        timeout_seconds: int = 10,
        transport: Any | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.cache_ttl_hours = cache_ttl_hours
        self.timeout_seconds = timeout_seconds
        self.offline_mode = offline_mode
        self._transport = transport
        self._cache: dict[str, _CacheEntry] = {}
        self._offline_snapshots: dict[str, Any] = {}

    def plugin_details_url(self, plugin_id: str) -> str:
        return f"{self.url}/plugins/{plugin_id}"

    def search_plugins(
        self,
        query: str = "",
        category: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        params = {"query": query, "category": category, "limit": limit}
        cache_key = self._cache_key("search_plugins", params)
        data = self._get_json("/plugins/search", params=params, cache_key=cache_key, default=[])
        return data if isinstance(data, list) else []

    def get_plugin_details(self, plugin_id: str) -> dict[str, Any]:
        cache_key = self._cache_key("plugin_details", {"plugin_id": plugin_id})
        data = self._get_json(
            f"/plugins/{plugin_id}",
            params=None,
            cache_key=cache_key,
            default={},
        )
        return data if isinstance(data, dict) else {}

    def download_plugin(self, plugin_id: str, version: Optional[str] = None) -> bytes:
        params = {"version": version} if version else None
        cache_key = self._cache_key("download_plugin", {"plugin_id": plugin_id, "version": version})
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached if isinstance(cached, (bytes, bytearray)) else b""
        if self.offline_mode or not HTTPX_AVAILABLE:
            return self._offline_snapshots.get(cache_key, b"")

        try:
            with self._build_httpx_client() as client:
                response = client.get(f"{self.url}/plugins/{plugin_id}/download", params=params)
                response.raise_for_status()
            payload = response.content
            self._cache_set(cache_key, payload)
            self._offline_snapshots[cache_key] = payload
            return payload
        except Exception:
            fallback = self._offline_snapshots.get(cache_key, b"")
            return fallback if isinstance(fallback, (bytes, bytearray)) else b""

    def get_plugin_versions(self, plugin_id: str) -> list[dict[str, Any]]:
        cache_key = self._cache_key("plugin_versions", {"plugin_id": plugin_id})
        data = self._get_json(
            f"/plugins/{plugin_id}/versions",
            params=None,
            cache_key=cache_key,
            default=[],
        )
        return data if isinstance(data, list) else []

    def get_categories(self) -> list[str]:
        cache_key = self._cache_key("categories", {})
        data = self._get_json("/plugins/categories", params=None, cache_key=cache_key, default=[])
        if isinstance(data, list):
            return [str(item) for item in data]
        return []

    def clear_cache(self) -> None:
        self._cache.clear()

    def set_offline_mode(self, enabled: bool) -> None:
        self.offline_mode = enabled

    def _get_json(
        self,
        path: str,
        *,
        params: Optional[dict[str, Any]],
        cache_key: str,
        default: Any,
    ) -> Any:
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if self.offline_mode or not HTTPX_AVAILABLE:
            return self._offline_snapshots.get(cache_key, default)

        try:
            with self._build_httpx_client() as client:
                response = client.get(f"{self.url}{path}", params=params)
                response.raise_for_status()
            payload = response.json()
            self._cache_set(cache_key, payload)
            self._offline_snapshots[cache_key] = payload
            return payload
        except Exception:
            return self._offline_snapshots.get(cache_key, default)

    def _build_httpx_client(self):
        kwargs: dict[str, Any] = {"timeout": self.timeout_seconds}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def _cache_key(self, method_name: str, params: dict[str, Any]) -> str:
        sorted_items = sorted((key, value) for key, value in params.items() if value is not None)
        payload = "&".join(f"{key}={value}" for key, value in sorted_items)
        return f"{method_name}:{payload}"

    def _cache_get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.time():
            self._cache.pop(key, None)
            return None
        return entry.value

    def _cache_set(self, key: str, value: Any) -> None:
        ttl_seconds = max(1, int(self.cache_ttl_hours * 3600))
        self._cache[key] = _CacheEntry(value=value, expires_at=time.time() + ttl_seconds)
