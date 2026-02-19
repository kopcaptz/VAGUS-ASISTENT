"""Tests for marketplace client with cache and offline mode."""

from __future__ import annotations

import json

import httpx

from vagus.plugins.marketplace import MarketplaceClient


def _build_transport(call_counter: dict[str, int]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        call_counter[path] = call_counter.get(path, 0) + 1

        if path == "/plugins/search":
            payload = [{"plugin_id": "plugin_a", "name": "Plugin A", "category": "utility"}]
            return httpx.Response(200, json=payload)
        if path == "/plugins/plugin_a":
            payload = {"plugin_id": "plugin_a", "name": "Plugin A", "avg_rating": 4.8}
            return httpx.Response(200, json=payload)
        if path == "/plugins/plugin_a/versions":
            payload = [{"version": "1.0.0"}, {"version": "0.9.0"}]
            return httpx.Response(200, json=payload)
        if path == "/plugins/categories":
            return httpx.Response(200, json=["utility", "productivity"])
        if path == "/plugins/plugin_a/download":
            return httpx.Response(200, content=b"plugin-binary-data")
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


def test_marketplace_client_search_and_cache():
    calls: dict[str, int] = {}
    client = MarketplaceClient(
        url="https://mock.marketplace",
        cache_ttl_hours=1,
        transport=_build_transport(calls),
    )

    first = client.search_plugins(query="plugin", category="utility", limit=10)
    second = client.search_plugins(query="plugin", category="utility", limit=10)

    assert first and second
    assert calls["/plugins/search"] == 1, "Expected second result to be returned from cache"


def test_marketplace_client_get_details_and_versions():
    client = MarketplaceClient(
        url="https://mock.marketplace",
        cache_ttl_hours=1,
        transport=_build_transport({}),
    )
    details = client.get_plugin_details("plugin_a")
    versions = client.get_plugin_versions("plugin_a")
    assert details["plugin_id"] == "plugin_a"
    assert versions[0]["version"] == "1.0.0"


def test_marketplace_client_download_plugin_bytes():
    client = MarketplaceClient(
        url="https://mock.marketplace",
        cache_ttl_hours=1,
        transport=_build_transport({}),
    )
    content = client.download_plugin("plugin_a", version="1.0.0")
    assert content == b"plugin-binary-data"


def test_marketplace_client_categories():
    client = MarketplaceClient(
        url="https://mock.marketplace",
        cache_ttl_hours=1,
        transport=_build_transport({}),
    )
    categories = client.get_categories()
    assert categories == ["utility", "productivity"]


def test_marketplace_client_offline_uses_cached_snapshots():
    client = MarketplaceClient(
        url="https://mock.marketplace",
        cache_ttl_hours=1,
        transport=_build_transport({}),
    )
    online = client.search_plugins(query="plugin", category="utility", limit=5)
    assert online

    client.set_offline_mode(True)
    offline = client.search_plugins(query="plugin", category="utility", limit=5)
    assert offline == online


def test_marketplace_client_offline_without_cache_returns_defaults():
    client = MarketplaceClient(
        url="https://mock.marketplace",
        cache_ttl_hours=1,
        offline_mode=True,
    )
    assert client.search_plugins(query="x", category=None, limit=3) == []
    assert client.get_plugin_details("missing") == {}
    assert client.get_plugin_versions("missing") == []
    assert client.download_plugin("missing", version=None) == b""
