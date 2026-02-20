"""Tests for plugin management API endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vagus.plugins.manager import PluginManager


def _create_test_plugin(plugin_dir: Path, *, name: str, version: str = "1.0.0") -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": version,
        "author": "API Tests",
        "description": "Plugin API test fixture",
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
    yield manager


def test_plugins_endpoints_require_admin(client, user_headers, plugin_manager):
    no_auth_resp = client.get("/api/v1/plugins")
    assert no_auth_resp.status_code == 401

    user_resp = client.get("/api/v1/plugins", headers=user_headers)
    assert user_resp.status_code == 403


def test_plugin_install_list_toggle_config_uninstall(
    client,
    admin_headers,
    plugin_manager,
    tmp_path: Path,
):
    source_plugin = tmp_path / "source_plugin"
    _create_test_plugin(source_plugin, name="api_plugin")

    install_resp = client.post(
        "/api/v1/plugins/install",
        json={"source": str(source_plugin)},
        headers=admin_headers,
    )
    assert install_resp.status_code == 201
    install_payload = install_resp.json()
    assert install_payload["name"] == "api_plugin"
    assert install_payload["status"] == "ENABLED"
    assert install_payload["enabled"] is True

    list_resp = client.get("/api/v1/plugins", headers=admin_headers)
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert any(item["name"] == "api_plugin" for item in listed)

    details_resp = client.get("/api/v1/plugins/api_plugin", headers=admin_headers)
    assert details_resp.status_code == 200
    assert details_resp.json()["name"] == "api_plugin"

    disable_resp = client.post("/api/v1/plugins/api_plugin/disable", headers=admin_headers)
    assert disable_resp.status_code == 200
    assert disable_resp.json()["enabled"] is False
    assert disable_resp.json()["status"] == "DISABLED"

    enable_resp = client.post("/api/v1/plugins/api_plugin/enable", headers=admin_headers)
    assert enable_resp.status_code == 200
    assert enable_resp.json()["enabled"] is True
    assert enable_resp.json()["status"] == "ENABLED"

    get_config_resp = client.get("/api/v1/plugins/api_plugin/config", headers=admin_headers)
    assert get_config_resp.status_code == 200
    assert get_config_resp.json()["settings"] == {}

    update_config_resp = client.put(
        "/api/v1/plugins/api_plugin/config",
        json={
            "settings": {"mode": "safe"},
            "secrets": {"token": "secret-value"},
            "ui_schema": {"fields": ["mode"]},
        },
        headers=admin_headers,
    )
    assert update_config_resp.status_code == 200
    updated_config = update_config_resp.json()
    assert updated_config["settings"]["mode"] == "safe"
    assert updated_config["secrets"]["token"] == "secret-value"
    assert updated_config["ui_schema"]["fields"] == ["mode"]

    delete_resp = client.delete("/api/v1/plugins/api_plugin", headers=admin_headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["plugin_name"] == "api_plugin"
    assert delete_resp.json()["status"] == "deleted"

    list_after_delete = client.get("/api/v1/plugins", headers=admin_headers)
    assert list_after_delete.status_code == 200
    assert not any(item["name"] == "api_plugin" for item in list_after_delete.json())


def test_plugin_not_found_returns_404(client, admin_headers, plugin_manager):
    response = client.get("/api/v1/plugins/missing-plugin", headers=admin_headers)
    assert response.status_code == 404
