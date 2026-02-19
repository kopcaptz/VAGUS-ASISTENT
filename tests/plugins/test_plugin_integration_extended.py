"""Extended integration tests for plugin ecosystem components."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from vagus.plugins.backup import PluginBackupManager
from vagus.plugins.dependencies import PluginDependencyResolver
from vagus.plugins.hooks import HookSystem
from vagus.plugins.hot_reload import HotReloadConfig, HotReloadManager
from vagus.plugins.loader import LocalLoader
from vagus.plugins.marketplace import MarketplaceClient, create_marketplace_app
from vagus.plugins.registry import PluginRegistry
from vagus.plugins.tools import PluginTemplateGenerator


def test_marketplace_client_works_with_marketplace_api_and_offline_cache(tmp_path: Path):
    app = create_marketplace_app(db_path=tmp_path / "market.db")
    api_client = TestClient(app)
    upload_payload = {
        "plugin_id": "integration_plugin",
        "name": "Integration Plugin",
        "description": "for integration tests",
        "category": "testing",
        "author": "tests",
        "version": "1.0.0",
        "download_url": "https://example.com/integration_plugin.zip",
        "changelog": "initial",
        "metadata": {},
        "rating": 5.0,
        "review": "excellent",
    }
    assert api_client.post("/plugins/upload", json=upload_payload).status_code == 201

    def _handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.query:
            path = f"{path}?{request.url.query.decode()}"
        response = api_client.request(
            request.method,
            path,
            content=request.content,
            headers=request.headers,
        )
        return httpx.Response(
            status_code=response.status_code,
            content=response.content,
            headers={"content-type": response.headers.get("content-type", "application/json")},
        )

    transport = httpx.MockTransport(_handler)

    client = MarketplaceClient(url="http://testserver", transport=transport)
    found = client.search_plugins(query="integration", category="testing", limit=5)
    assert found and found[0]["plugin_id"] == "integration_plugin"
    online_details = client.get_plugin_details("integration_plugin")
    assert online_details["plugin_id"] == "integration_plugin"

    client.set_offline_mode(True)
    details = client.get_plugin_details("integration_plugin")
    assert details["plugin_id"] == "integration_plugin"


def test_template_hot_reload_flow(tmp_path: Path):
    generator = PluginTemplateGenerator(destination_root=tmp_path)
    plugin_dir = generator.create("integration_hot", template="basic")

    registry = PluginRegistry()
    registry.clear()
    hook_system = HookSystem()
    loader = LocalLoader()

    plugin = loader.load(plugin_dir)
    registry.register(plugin)
    manager = HotReloadManager(
        registry=registry,
        loader=loader,
        hook_system=hook_system,
        config=HotReloadConfig(enabled=True, debounce_ms=10),
    )
    manager.register_plugin(plugin)

    result = asyncio.run(hook_system.on_message_received({"text": "hello"}))
    assert result["plugin"] == "integration_hot"


def test_backup_import_and_dependency_resolution(tmp_path: Path):
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    plugin_a = plugins_dir / "plugin_a"
    plugin_b = plugins_dir / "plugin_b"
    plugin_a.mkdir()
    plugin_b.mkdir()
    (plugin_a / "manifest.json").write_text(json.dumps({"name": "plugin_a"}), encoding="utf-8")
    (plugin_b / "manifest.json").write_text(json.dumps({"name": "plugin_b"}), encoding="utf-8")

    manager = PluginBackupManager(backup_root=tmp_path / "backups")
    archive = manager.export_plugins([plugin_a, plugin_b], tmp_path / "archive" / "plugins.zip")
    restored = manager.import_plugins(archive, tmp_path / "restored")
    assert sorted(path.name for path in restored) == ["plugin_a", "plugin_b"]

    resolver = PluginDependencyResolver()
    resolver.add_plugin("plugin_b", "1.0.0", [])
    resolver.add_plugin("plugin_a", "1.0.0", ["plugin_b>=1.0.0"])
    assert resolver.resolve(["plugin_a"]) == ["plugin_b", "plugin_a"]
