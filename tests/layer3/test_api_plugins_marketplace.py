"""Tests for plugin marketplace/search/dependency/statistics API endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from vagus.plugins.manager import PluginManager
from vagus.plugins.marketplace import MarketplaceClient


def _create_test_plugin(
    plugin_dir: Path,
    *,
    name: str,
    version: str = "1.0.0",
    dependencies: list[str] | None = None,
) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": version,
        "author": "API Tests",
        "description": f"Plugin fixture for {name}",
        "dependencies": dependencies or [],
        "python_version": ">=3.10",
        "vagus_version": ">=0.1.0",
        "entry_point": "plugin:PluginEntry",
        "hooks": [],
        "permissions": [],
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "plugin.py").write_text(
        "class PluginEntry:\n"
        "    pass\n",
        encoding="utf-8",
    )


def _build_marketplace_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path == "/plugins/search":
            query = request.url.params.get("query", "")
            category = request.url.params.get("category") or "general"
            return httpx.Response(
                200,
                json=[
                    {
                        "plugin_id": "marketplace-demo",
                        "name": "Marketplace Demo",
                        "description": f"Result for {query or 'all'}",
                        "category": category,
                        "author": "Marketplace",
                        "latest_version": "1.2.3",
                        "avg_rating": 4.8,
                        "review_count": 11,
                    }
                ],
            )

        if path == "/plugins/categories":
            return httpx.Response(200, json=["automation", "ai", "monitoring"])

        if path == "/plugins/marketplace-demo":
            return httpx.Response(
                200,
                json={
                    "plugin_id": "marketplace-demo",
                    "name": "Marketplace Demo",
                    "description": "Detailed plugin payload",
                    "category": "automation",
                    "author": "Marketplace",
                    "latest_version": "1.2.3",
                    "avg_rating": 4.8,
                    "review_count": 11,
                    "metadata": {"downloads": 1200},
                    "versions": [{"version": "1.2.3", "download_url": "https://example.test/plugin.zip"}],
                    "reviews": [{"rating": 5, "review": "Great plugin!"}],
                    "download_url": "https://example.test/plugin.zip",
                },
            )

        if path == "/plugins/not-found":
            return httpx.Response(404, json={"detail": "not found"})

        return httpx.Response(404, json={"detail": "unknown path"})

    return httpx.MockTransport(handler)


@pytest.fixture()
def plugin_manager(app, tmp_path: Path):
    manager = PluginManager(install_root=tmp_path / "plugin_store")
    app.state.plugin_manager = manager
    return manager


@pytest.fixture()
def fake_marketplace(app):
    client = MarketplaceClient(
        url="https://plugins.vagus.ai",
        cache_ttl_hours=24,
        transport=_build_marketplace_transport(),
    )
    app.state.marketplace_client = client
    return client


def test_marketplace_endpoints_require_admin(client, user_headers, plugin_manager, fake_marketplace):
    _ = plugin_manager
    _ = fake_marketplace

    no_auth = client.get("/api/v1/plugins/marketplace/search?q=test")
    assert no_auth.status_code == 401

    user_resp = client.get("/api/v1/plugins/marketplace/search?q=test", headers=user_headers)
    assert user_resp.status_code == 403


def test_marketplace_search_categories_trending_details(
    client,
    admin_headers,
    plugin_manager,
    fake_marketplace,
):
    _ = plugin_manager
    _ = fake_marketplace

    search_resp = client.get(
        "/api/v1/plugins/marketplace/search?q=demo&category=automation&limit=5",
        headers=admin_headers,
    )
    assert search_resp.status_code == 200
    search_payload = search_resp.json()
    assert search_payload[0]["plugin_id"] == "marketplace-demo"
    assert search_payload[0]["category"] == "automation"

    categories_resp = client.get("/api/v1/plugins/marketplace/categories", headers=admin_headers)
    assert categories_resp.status_code == 200
    assert "automation" in categories_resp.json()

    trending_resp = client.get("/api/v1/plugins/marketplace/trending?limit=3", headers=admin_headers)
    assert trending_resp.status_code == 200
    assert trending_resp.json()[0]["plugin_id"] == "marketplace-demo"

    details_resp = client.get("/api/v1/plugins/marketplace/marketplace-demo", headers=admin_headers)
    assert details_resp.status_code == 200
    details_payload = details_resp.json()
    assert details_payload["plugin_id"] == "marketplace-demo"
    assert details_payload["metadata"]["downloads"] == 1200

    missing_details_resp = client.get("/api/v1/plugins/marketplace/not-found", headers=admin_headers)
    assert missing_details_resp.status_code == 404


def test_marketplace_install_endpoint_uses_plugin_manager(
    client,
    admin_headers,
    app,
    plugin_manager,
    fake_marketplace,
):
    _ = fake_marketplace
    captured: dict[str, Any] = {}

    def _fake_install(
        source: str,
        *,
        version: str | None = None,
        marketplace_client: Any = None,
    ) -> dict[str, Any]:
        captured["source"] = source
        captured["version"] = version
        captured["marketplace_client"] = marketplace_client
        return {
            "name": "marketplace-demo",
            "version": version or "1.2.3",
            "status": "ENABLED",
            "enabled": True,
            "author": "Marketplace",
            "description": "Installed from marketplace",
            "source": source,
            "path": "/tmp/marketplace-demo",
            "installed_at": None,
            "load_error": None,
        }

    plugin_manager.install_plugin = _fake_install  # type: ignore[method-assign]

    install_resp = client.post(
        "/api/v1/plugins/marketplace/marketplace-demo/install",
        json={"version": "1.2.3"},
        headers=admin_headers,
    )
    assert install_resp.status_code == 201
    assert install_resp.json()["name"] == "marketplace-demo"
    assert captured["source"] == "marketplace-demo"
    assert captured["version"] == "1.2.3"
    assert captured["marketplace_client"] is app.state.marketplace_client


def test_dependencies_and_statistics_endpoints(
    client,
    admin_headers,
    plugin_manager,
    fake_marketplace,
    tmp_path: Path,
):
    _ = fake_marketplace

    dep_source = tmp_path / "dep_plugin"
    main_source = tmp_path / "main_plugin"
    _create_test_plugin(dep_source, name="pip", version="1.0.0")
    _create_test_plugin(
        main_source,
        name="main-plugin",
        version="1.0.0",
        dependencies=["pip>=1000.0"],
    )

    plugin_manager.install_plugin(str(dep_source))
    plugin_manager.install_plugin(str(main_source))

    deps_resp = client.get("/api/v1/plugins/main-plugin/dependencies", headers=admin_headers)
    assert deps_resp.status_code == 200
    deps_payload = deps_resp.json()
    assert deps_payload["plugin_name"] == "main-plugin"
    assert "pip>=1000.0" in deps_payload["dependencies"]
    assert deps_payload["conflicts"].get("pip")

    stats_resp = client.get("/api/v1/plugins/statistics", headers=admin_headers)
    assert stats_resp.status_code == 200
    stats_payload = stats_resp.json()
    summary = stats_payload["summary"]
    assert summary["installed_total"] == 2
    assert summary["enabled_total"] == 2
    assert stats_payload["trending"][0]["plugin_id"] == "marketplace-demo"


def test_dependency_management_endpoints_resolve_update_conflicts_and_bulk(
    client,
    admin_headers,
    plugin_manager,
    tmp_path: Path,
):
    dep_source = tmp_path / "dep_resolve_plugin"
    main_source = tmp_path / "main_resolve_plugin"
    bulk_one_source = tmp_path / "bulk_one_plugin"
    bulk_two_source = tmp_path / "bulk_two_plugin"

    _create_test_plugin(dep_source, name="pip", version="1.0.0")
    _create_test_plugin(
        main_source,
        name="main-resolve-plugin",
        version="1.0.0",
        dependencies=["pip>=1000.0"],
    )
    _create_test_plugin(bulk_one_source, name="bulk-one", version="1.0.0")
    _create_test_plugin(bulk_two_source, name="bulk-two", version="1.0.0")

    plugin_manager.install_plugin(str(dep_source))
    plugin_manager.install_plugin(str(main_source))
    plugin_manager.install_plugin(str(bulk_one_source))
    plugin_manager.install_plugin(str(bulk_two_source))

    conflicts_resp = client.get(
        "/api/v1/plugins/main-resolve-plugin/dependencies/conflicts",
        headers=admin_headers,
    )
    assert conflicts_resp.status_code == 200
    conflicts_payload = conflicts_resp.json()
    assert conflicts_payload["plugin_name"] == "main-resolve-plugin"
    assert "pip" in conflicts_payload["conflicts"]
    assert conflicts_payload["lock_content"]

    resolve_resp = client.post(
        "/api/v1/plugins/main-resolve-plugin/dependencies/resolve",
        json={"strategy": "prefer-installed", "pin_versions": True, "dry_run": False},
        headers=admin_headers,
    )
    assert resolve_resp.status_code == 200
    resolve_payload = resolve_resp.json()
    assert resolve_payload["applied_updates"]["pip"] == "==1.0.0"

    update_resp = client.post(
        "/api/v1/plugins/main-resolve-plugin/dependencies/update",
        json={
            "updates": {"pip": "==1.0.0"},
            "pin_versions": True,
            "dry_run": False,
            "export_lock": True,
        },
        headers=admin_headers,
    )
    assert update_resp.status_code == 200
    update_payload = update_resp.json()
    assert "pip==1.0.0" in update_payload["updated_dependencies"]
    assert "pip==1.0.0" in (update_payload.get("lock_content") or "")

    import_lock_resp = client.post(
        "/api/v1/plugins/main-resolve-plugin/dependencies/update",
        json={
            "updates": {},
            "import_lock_content": "pip==1.0.0\nrequests>=2.0.0\n",
            "pin_versions": True,
            "dry_run": True,
            "export_lock": True,
        },
        headers=admin_headers,
    )
    assert import_lock_resp.status_code == 200
    import_payload = import_lock_resp.json()
    assert "requests>=2.0.0" in import_payload["updated_dependencies"]

    bulk_resp = client.post(
        "/api/v1/plugins/dependencies/bulk-update",
        json={
            "operations": [
                {"plugin_name": "bulk-one", "updates": {"pip": "==1.0.0"}, "pin_versions": True},
                {"plugin_name": "bulk-two", "updates": {"bad dependency": "1.0.0"}, "pin_versions": True},
            ],
            "dry_run": False,
            "rollback_on_error": True,
            "allow_conflicts": True,
            "export_lock": True,
        },
        headers=admin_headers,
    )
    assert bulk_resp.status_code == 200
    bulk_payload = bulk_resp.json()
    assert bulk_payload["rolled_back"] is True
    assert bulk_payload["errors"]

    bulk_one_path = Path(str(plugin_manager.get_plugin("bulk-one")["path"]))
    bulk_one_manifest = json.loads((bulk_one_path / "manifest.json").read_text(encoding="utf-8"))
    assert bulk_one_manifest.get("dependencies") == []
