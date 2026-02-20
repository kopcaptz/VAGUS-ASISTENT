"""Tests for dashboard plugin API client methods."""

from __future__ import annotations

import httpx

from dashboard.utils.api_client import VagusAPIClient


def _build_plugin_transport() -> httpx.MockTransport:
    plugin_state = {
        "name": "demo-plugin",
        "version": "1.0.0",
        "status": "ENABLED",
        "enabled": True,
        "author": "Tests",
        "description": "Plugin from mock API",
    }
    plugin_config = {"settings": {"mode": "safe"}, "secrets": {}, "ui_schema": {}}
    marketplace_item = {
        "plugin_id": "marketplace-demo",
        "name": "Marketplace Demo",
        "description": "Marketplace plugin",
        "category": "automation",
        "author": "Marketplace",
        "avg_rating": 4.7,
        "review_count": 12,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method.upper()

        if path == "/api/v1/plugins" and method == "GET":
            return httpx.Response(200, json=[plugin_state])

        if path == "/api/v1/plugins/install" and method == "POST":
            payload = request.read().decode("utf-8")
            if "demo-plugin" in payload:
                return httpx.Response(201, json=plugin_state)
            return httpx.Response(400, json={"detail": "install failed"})

        if path == "/api/v1/plugins/demo-plugin" and method == "GET":
            return httpx.Response(200, json=plugin_state)

        if path == "/api/v1/plugins/demo-plugin/disable" and method == "POST":
            plugin_state["enabled"] = False
            plugin_state["status"] = "DISABLED"
            return httpx.Response(200, json=plugin_state)

        if path == "/api/v1/plugins/demo-plugin/enable" and method == "POST":
            plugin_state["enabled"] = True
            plugin_state["status"] = "ENABLED"
            return httpx.Response(200, json=plugin_state)

        if path == "/api/v1/plugins/demo-plugin/config" and method == "GET":
            return httpx.Response(200, json=plugin_config)

        if path == "/api/v1/plugins/demo-plugin/config" and method == "PUT":
            payload = request.read().decode("utf-8")
            if "unsafe" in payload:
                plugin_config["settings"]["mode"] = "unsafe"
            return httpx.Response(200, json=plugin_config)

        if path == "/api/v1/plugins/demo-plugin" and method == "DELETE":
            return httpx.Response(200, json={"plugin_name": "demo-plugin", "status": "deleted"})

        if path == "/api/v1/plugins/marketplace/search" and method == "GET":
            return httpx.Response(200, json=[marketplace_item])

        if path == "/api/v1/plugins/marketplace/categories" and method == "GET":
            return httpx.Response(200, json=["automation", "ai"])

        if path == "/api/v1/plugins/marketplace/marketplace-demo" and method == "GET":
            return httpx.Response(
                200,
                json={
                    **marketplace_item,
                    "metadata": {"downloads": 100},
                    "versions": [{"version": "1.0.0"}],
                    "reviews": [{"rating": 5, "review": "great"}],
                },
            )

        if path == "/api/v1/plugins/marketplace/marketplace-demo/install" and method == "POST":
            return httpx.Response(201, json=plugin_state)

        if path == "/api/v1/plugins/marketplace/trending" and method == "GET":
            return httpx.Response(200, json=[marketplace_item])

        if path == "/api/v1/plugins/demo-plugin/dependencies" and method == "GET":
            return httpx.Response(
                200,
                json={
                    "plugin_name": "demo-plugin",
                    "dependencies": ["dep-plugin>=1.0.0"],
                    "install_order": ["dep-plugin", "demo-plugin"],
                    "graph": {"demo-plugin": ["dep-plugin"], "dep-plugin": []},
                    "edges": [{"source": "demo-plugin", "target": "dep-plugin"}],
                    "conflicts": {},
                    "missing_dependencies": [],
                },
            )

        if path == "/api/v1/plugins/statistics" and method == "GET":
            return httpx.Response(
                200,
                json={
                    "summary": {"installed_total": 1, "enabled_total": 1, "marketplace_offline_mode": False},
                    "popularity": [{"plugin_name": "demo-plugin", "calls": 10}],
                    "trending": [marketplace_item],
                },
            )

        if path == "/api/v1/plugins/demo-plugin/dependencies/conflicts" and method == "GET":
            return httpx.Response(
                200,
                json={
                    "plugin_name": "demo-plugin",
                    "conflicts": {"dep-plugin": [">=2.0.0"]},
                    "missing_dependencies": [],
                    "health_checks": [],
                    "recommendations": ["Update dep-plugin"],
                    "lock_file_path": "/tmp/requirements.txt",
                    "lock_content": "dep-plugin>=2.0.0\n",
                },
            )

        if path == "/api/v1/plugins/demo-plugin/dependencies/resolve" and method == "POST":
            return httpx.Response(
                200,
                json={
                    "plugin_name": "demo-plugin",
                    "updated_dependencies": ["dep-plugin==2.0.0"],
                    "applied_updates": {"dep-plugin": "==2.0.0"},
                    "dry_run": False,
                    "conflicts": {},
                    "missing_dependencies": [],
                    "health_checks": [],
                    "recommendations": [],
                    "lock_file_path": "/tmp/requirements.txt",
                    "lock_content": "dep-plugin==2.0.0\n",
                },
            )

        if path == "/api/v1/plugins/demo-plugin/dependencies/update" and method == "POST":
            return httpx.Response(
                200,
                json={
                    "plugin_name": "demo-plugin",
                    "updated_dependencies": ["dep-plugin==2.1.0"],
                    "applied_updates": {"dep-plugin": "==2.1.0"},
                    "dry_run": False,
                    "conflicts": {},
                    "missing_dependencies": [],
                    "health_checks": [],
                    "recommendations": [],
                    "lock_file_path": "/tmp/requirements.txt",
                    "lock_content": "dep-plugin==2.1.0\n",
                },
            )

        if path == "/api/v1/plugins/dependencies/bulk-update" and method == "POST":
            return httpx.Response(
                200,
                json={
                    "updated": [
                        {
                            "plugin_name": "demo-plugin",
                            "updated_dependencies": ["dep-plugin==2.1.0"],
                            "applied_updates": {"dep-plugin": "==2.1.0"},
                            "dry_run": False,
                            "conflicts": {},
                            "missing_dependencies": [],
                            "health_checks": [],
                            "recommendations": [],
                            "lock_file_path": "/tmp/requirements.txt",
                            "lock_content": "dep-plugin==2.1.0\n",
                        }
                    ],
                    "errors": [],
                    "rolled_back": False,
                },
            )

        if path == "/api/v1/plugins/hot-reload/status" and method == "GET":
            return httpx.Response(
                200,
                json={
                    "enabled": True,
                    "running": True,
                    "watchdog_available": True,
                    "watch_directories": ["./plugins"],
                    "debounce_ms": 500,
                    "events_total": 12,
                    "recent_logs": [{"timestamp": "2026-01-01T00:00:00Z", "event_type": "plugin_reloaded"}],
                    "plugin_health": [],
                    "performance": {"recommendations": []},
                    "alerts": [],
                    "alerting": {"channels": {"email": False, "telegram": False, "webhook": False}},
                },
            )

        if path == "/api/v1/plugins/hot-reload/enable" and method == "POST":
            return httpx.Response(
                200,
                json={
                    "enabled": True,
                    "running": True,
                    "watchdog_available": True,
                    "message": "Hot-reload enabled",
                },
            )

        if path == "/api/v1/plugins/hot-reload/disable" and method == "POST":
            return httpx.Response(
                200,
                json={
                    "enabled": False,
                    "running": False,
                    "watchdog_available": True,
                    "message": "Hot-reload disabled",
                },
            )

        if path == "/api/v1/plugins/hot-reload/logs" and method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "event_type": "plugin_reloaded",
                        "plugin_name": "demo-plugin",
                        "success": True,
                        "details": {},
                    }
                ],
            )

        if path == "/api/v1/plugins/demo-plugin/reload-history" and method == "GET":
            return httpx.Response(
                200,
                json={
                    "plugin_name": "demo-plugin",
                    "history": [
                        {
                            "timestamp": "2026-01-01T00:00:00Z",
                            "event_type": "plugin_reloaded",
                            "plugin_name": "demo-plugin",
                            "success": True,
                            "details": {},
                        }
                    ],
                },
            )

        if path == "/api/v1/plugins/demo-plugin/reload-now" and method == "POST":
            return httpx.Response(
                200,
                json={
                    "plugin_name": "demo-plugin",
                    "reloaded": True,
                    "message": "Plugin reloaded successfully",
                    "event": {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "event_type": "plugin_reloaded",
                        "plugin_name": "demo-plugin",
                        "success": True,
                        "details": {},
                    },
                },
            )

        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


def test_dashboard_plugin_client_methods():
    transport = _build_plugin_transport()
    client = VagusAPIClient(
        base_url="http://localhost:8000/api/v1",
        token="test-token",
        transport=transport,
    )

    listed = client.get_plugins()
    assert listed[0]["name"] == "demo-plugin"

    installed = client.install_plugin("demo-plugin", version="1.0.0")
    assert installed["name"] == "demo-plugin"

    details = client.get_plugin("demo-plugin")
    assert details["status"] == "ENABLED"

    disabled = client.disable_plugin("demo-plugin")
    assert disabled["status"] == "DISABLED"
    assert disabled["enabled"] is False

    enabled = client.enable_plugin("demo-plugin")
    assert enabled["status"] == "ENABLED"
    assert enabled["enabled"] is True

    config = client.get_plugin_config("demo-plugin")
    assert config["settings"]["mode"] == "safe"

    updated = client.update_plugin_config("demo-plugin", settings={"mode": "unsafe"})
    assert updated["settings"]["mode"] == "unsafe"

    search_results = client.marketplace_search_plugins(query="demo", category="automation", limit=5)
    assert search_results[0]["plugin_id"] == "marketplace-demo"

    categories = client.marketplace_categories()
    assert "automation" in categories

    details_marketplace = client.marketplace_plugin_details("marketplace-demo")
    assert details_marketplace["metadata"]["downloads"] == 100

    installed_marketplace = client.marketplace_install_plugin("marketplace-demo")
    assert installed_marketplace["name"] == "demo-plugin"

    trending = client.marketplace_trending_plugins(limit=10)
    assert trending[0]["plugin_id"] == "marketplace-demo"

    dependencies = client.get_plugin_dependencies("demo-plugin")
    assert dependencies["plugin_name"] == "demo-plugin"

    conflicts = client.get_plugin_dependency_conflicts("demo-plugin")
    assert conflicts["plugin_name"] == "demo-plugin"
    assert conflicts["conflicts"]["dep-plugin"] == [">=2.0.0"]

    resolved = client.resolve_plugin_dependencies("demo-plugin", pin_versions=True)
    assert resolved["applied_updates"]["dep-plugin"] == "==2.0.0"

    updated_dependencies = client.update_plugin_dependencies(
        "demo-plugin",
        updates={"dep-plugin": "==2.1.0"},
        pin_versions=True,
    )
    assert updated_dependencies["applied_updates"]["dep-plugin"] == "==2.1.0"

    bulk_result = client.bulk_update_plugin_dependencies(
        operations=[{"plugin_name": "demo-plugin", "updates": {"dep-plugin": "==2.1.0"}}]
    )
    assert bulk_result["rolled_back"] is False
    assert bulk_result["updated"][0]["plugin_name"] == "demo-plugin"

    hot_reload_status = client.get_hot_reload_status()
    assert hot_reload_status["enabled"] is True

    hot_reload_enable = client.enable_hot_reload()
    assert hot_reload_enable["running"] is True

    hot_reload_disable = client.disable_hot_reload()
    assert hot_reload_disable["enabled"] is False

    hot_reload_logs = client.get_hot_reload_logs(limit=50, plugin_name="demo-plugin")
    assert hot_reload_logs[0]["event_type"] == "plugin_reloaded"

    reload_history = client.get_plugin_reload_history("demo-plugin", limit=50)
    assert reload_history["plugin_name"] == "demo-plugin"

    reload_now = client.reload_plugin_now("demo-plugin")
    assert reload_now["reloaded"] is True

    assert client.websocket_root_url == "ws://localhost:8000"

    statistics = client.get_plugin_statistics()
    assert statistics["summary"]["installed_total"] == 1

    deleted = client.uninstall_plugin("demo-plugin")
    assert deleted["status"] == "deleted"
