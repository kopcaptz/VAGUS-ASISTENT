"""HTTP client for Vagus plugin marketplace."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
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
        sample_data_path: str | Path | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.cache_ttl_hours = cache_ttl_hours
        self.timeout_seconds = timeout_seconds
        self.offline_mode = offline_mode
        self._transport = transport
        self._cache: dict[str, _CacheEntry] = {}
        self._offline_snapshots: dict[str, Any] = {}

        default_path = Path(__file__).resolve().parents[4] / "data" / "marketplace_sample.json"
        self.sample_data_path = Path(sample_data_path) if sample_data_path is not None else default_path
        self._sample_plugins = self._load_sample_plugins()

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

    def get_trending_plugins(
        self,
        *,
        limit: int = 20,
        category: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Returns top marketplace plugins by rating/review signal.
        Backed by marketplace search endpoint ordering.
        """
        return self.search_plugins(query="", category=category, limit=limit)

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
            fallback = self._offline_snapshots.get(cache_key)
            if isinstance(fallback, (bytes, bytearray)):
                return bytes(fallback)
            return self._offline_download_payload(plugin_id=plugin_id, version=version)

        try:
            with self._build_httpx_client() as client:
                response = client.get(f"{self.url}/plugins/{plugin_id}/download", params=params)
                response.raise_for_status()
            payload = response.content
            self._cache_set(cache_key, payload)
            self._offline_snapshots[cache_key] = payload
            self.offline_mode = False
            return payload
        except Exception:
            self.offline_mode = True
            fallback = self._offline_snapshots.get(cache_key)
            if isinstance(fallback, (bytes, bytearray)):
                return bytes(fallback)
            return self._offline_download_payload(plugin_id=plugin_id, version=version)

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
            if cache_key in self._offline_snapshots:
                return self._offline_snapshots[cache_key]
            return self._offline_payload(path=path, params=params, default=default)

        try:
            with self._build_httpx_client() as client:
                response = client.get(f"{self.url}{path}", params=params)
                response.raise_for_status()
            payload = response.json()
            self._cache_set(cache_key, payload)
            self._offline_snapshots[cache_key] = payload
            self.offline_mode = False
            return payload
        except Exception:
            self.offline_mode = True
            if cache_key in self._offline_snapshots:
                return self._offline_snapshots[cache_key]
            return self._offline_payload(path=path, params=params, default=default)

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

    def _load_sample_plugins(self) -> list[dict[str, Any]]:
        try:
            if not self.sample_data_path.exists():
                return []
            payload = json.loads(self.sample_data_path.read_text(encoding="utf-8"))
            plugins = payload.get("plugins", []) if isinstance(payload, dict) else []
            if not isinstance(plugins, list):
                return []
            result: list[dict[str, Any]] = []
            for item in plugins:
                if isinstance(item, dict) and item.get("plugin_id"):
                    result.append(item)
            return result
        except Exception:
            return []

    def _offline_payload(
        self,
        *,
        path: str,
        params: Optional[dict[str, Any]],
        default: Any,
    ) -> Any:
        if path == "/plugins/search":
            query = str((params or {}).get("query") or "").strip().lower()
            category = str((params or {}).get("category") or "").strip().lower()
            limit = max(1, int((params or {}).get("limit") or 20))
            items: list[dict[str, Any]] = []
            for plugin in self._sample_plugins:
                plugin_id = str(plugin.get("plugin_id", "")).lower()
                name = str(plugin.get("name", "")).lower()
                description = str(plugin.get("description", "")).lower()
                plugin_category = str(plugin.get("category", "")).lower()
                if category and plugin_category != category:
                    continue
                if query and query not in plugin_id and query not in name and query not in description:
                    continue
                items.append(self._summary_from_sample(plugin))
            items.sort(key=lambda x: (float(x.get("avg_rating", 0.0)), int(x.get("review_count", 0))), reverse=True)
            return items[:limit]

        if path == "/plugins/categories":
            categories = sorted(
                {
                    str(plugin.get("category", "")).strip()
                    for plugin in self._sample_plugins
                    if str(plugin.get("category", "")).strip()
                }
            )
            return categories

        if path.startswith("/plugins/"):
            parts = [part for part in path.split("/") if part]
            if len(parts) >= 2:
                plugin_id = parts[1]
                plugin = self._sample_by_id(plugin_id)
                if plugin is None:
                    return default
                if len(parts) == 2:
                    return self._detail_from_sample(plugin)
                if len(parts) == 3 and parts[2] == "versions":
                    versions = plugin.get("versions", [])
                    return versions if isinstance(versions, list) else []

        return default

    def _offline_download_payload(self, *, plugin_id: str, version: Optional[str]) -> bytes:
        plugin = self._sample_by_id(plugin_id)
        if plugin is None:
            return b""
        resolved_version = version or str(plugin.get("latest_version", "")).strip()
        marker = f"offline-marketplace-package:{plugin_id}:{resolved_version}"
        return marker.encode("utf-8")

    def _sample_by_id(self, plugin_id: str) -> dict[str, Any] | None:
        for plugin in self._sample_plugins:
            if str(plugin.get("plugin_id", "")).strip() == plugin_id:
                return plugin
        return None

    @staticmethod
    def _summary_from_sample(plugin: dict[str, Any]) -> dict[str, Any]:
        return {
            "plugin_id": str(plugin.get("plugin_id", "")),
            "name": str(plugin.get("name", "")),
            "description": str(plugin.get("description", "")),
            "category": str(plugin.get("category", "general")),
            "author": str(plugin.get("author", "unknown")),
            "latest_version": str(plugin.get("latest_version", "")),
            "download_url": str(plugin.get("download_url", "")),
            "avg_rating": float(plugin.get("avg_rating", 0.0) or 0.0),
            "review_count": int(plugin.get("review_count", 0) or 0),
        }

    def _detail_from_sample(self, plugin: dict[str, Any]) -> dict[str, Any]:
        detail = self._summary_from_sample(plugin)
        detail["metadata"] = plugin.get("metadata", {}) if isinstance(plugin.get("metadata"), dict) else {}
        detail["versions"] = plugin.get("versions", []) if isinstance(plugin.get("versions"), list) else []
        detail["reviews"] = plugin.get("reviews", []) if isinstance(plugin.get("reviews"), list) else []
        return detail
