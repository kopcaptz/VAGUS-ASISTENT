"""Tests for plugin hot-reload monitoring API endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.websockets import WebSocketDisconnect

from vagus.plugins.manager import PluginManager


def _create_test_plugin(plugin_dir: Path, *, name: str, version: str = "1.0.0") -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": version,
        "author": "API Tests",
        "description": "Plugin hot-reload fixture",
        "dependencies": [],
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


@pytest.fixture()
def plugin_manager(app, tmp_path: Path):
    manager = PluginManager(install_root=tmp_path / "plugin_store")
    app.state.plugin_manager = manager
    return manager


def test_hot_reload_endpoints_require_admin(client, user_headers, plugin_manager):
    _ = plugin_manager
    no_auth = client.get("/api/v1/plugins/hot-reload/status")
    assert no_auth.status_code == 401

    user_resp = client.get("/api/v1/plugins/hot-reload/status", headers=user_headers)
    assert user_resp.status_code == 403

    user_disable = client.post("/api/v1/plugins/hot-reload/disable", headers=user_headers)
    assert user_disable.status_code == 403


def test_hot_reload_status_enable_disable_logs_and_history(
    client,
    admin_headers,
    plugin_manager,
    tmp_path: Path,
):
    source_plugin = tmp_path / "hot_plugin_source"
    _create_test_plugin(source_plugin, name="hot-plugin")
    plugin_manager.install_plugin(str(source_plugin))

    status_resp = client.get("/api/v1/plugins/hot-reload/status", headers=admin_headers)
    assert status_resp.status_code == 200
    status_payload = status_resp.json()
    assert "enabled" in status_payload
    assert "plugin_health" in status_payload
    assert "performance" in status_payload

    enable_resp = client.post("/api/v1/plugins/hot-reload/enable", headers=admin_headers)
    assert enable_resp.status_code == 200
    assert enable_resp.json()["enabled"] is True

    reload_now_resp = client.post("/api/v1/plugins/hot-plugin/reload-now", headers=admin_headers)
    assert reload_now_resp.status_code == 200
    reload_now_payload = reload_now_resp.json()
    assert reload_now_payload["plugin_name"] == "hot-plugin"
    assert "reloaded" in reload_now_payload

    history_resp = client.get("/api/v1/plugins/hot-plugin/reload-history", headers=admin_headers)
    assert history_resp.status_code == 200
    history_payload = history_resp.json()
    assert history_payload["plugin_name"] == "hot-plugin"
    assert isinstance(history_payload["history"], list)

    logs_resp = client.get("/api/v1/plugins/hot-reload/logs?limit=50", headers=admin_headers)
    assert logs_resp.status_code == 200
    assert isinstance(logs_resp.json(), list)

    disable_resp = client.post("/api/v1/plugins/hot-reload/disable", headers=admin_headers)
    assert disable_resp.status_code == 200
    assert disable_resp.json()["enabled"] is False


def test_plugins_realtime_updates_websocket(client, admin_token, plugin_manager):
    _ = plugin_manager
    with client.websocket_connect(f"/api/v1/plugins/ws/updates?token={admin_token}") as websocket:
        ack = websocket.receive_json()
        assert ack["type"] == "connection_ack"
        snapshot = websocket.receive_json()
        assert snapshot["type"] in {"status_snapshot", "hot_reload_event", "plugin_alert"}


def test_plugins_realtime_updates_websocket_rejects_invalid_token(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/plugins/ws/updates?token=invalid-token") as websocket:
            websocket.receive_json()
