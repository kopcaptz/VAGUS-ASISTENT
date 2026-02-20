"""Tests for plugin CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vagus.layer3.cli.commands import plugin as plugin_commands
from vagus.plugins.registry import PluginRegistry


def _create_test_plugin(plugin_dir: Path, *, name: str, version: str = "1.0.0") -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": version,
        "author": "Tests",
        "description": "CLI plugin command test",
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
def plugin_cli_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    install_root = tmp_path / "installed_plugins"
    state_file = install_root / "registry.json"

    monkeypatch.setattr(plugin_commands, "PLUGIN_INSTALL_ROOT", install_root)
    monkeypatch.setattr(plugin_commands, "PLUGIN_STATE_FILE", state_file)

    registry = PluginRegistry()
    registry.clear()
    yield install_root, state_file
    registry.clear()


def test_plugin_help_includes_all_commands():
    runner = CliRunner()
    result = runner.invoke(plugin_commands.app, ["--help"])
    assert result.exit_code == 0
    for command in ("create", "install", "list", "enable", "disable", "uninstall"):
        assert command in result.output


def test_plugin_install_local_and_list(plugin_cli_env, tmp_path: Path):
    install_root, state_file = plugin_cli_env
    plugin_dir = tmp_path / "local_plugin_src"
    _create_test_plugin(plugin_dir, name="local_plugin")

    runner = CliRunner()
    result = runner.invoke(plugin_commands.app, ["install", str(plugin_dir)])
    assert result.exit_code == 0
    assert "local_plugin" in result.output

    state_payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert "local_plugin" in state_payload["plugins"]
    assert (install_root / "local_plugin").exists()

    listed = runner.invoke(plugin_commands.app, ["list", "--all"])
    assert listed.exit_code == 0
    assert "local_plugin" in listed.output
    assert "ENABLED" in listed.output

    loaded = PluginRegistry().get_plugin("local_plugin")
    assert loaded is not None
    assert loaded.state.state.value == "ENABLED"


def test_plugin_enable_disable_flow(plugin_cli_env, tmp_path: Path):
    plugin_dir = tmp_path / "toggle_plugin_src"
    _create_test_plugin(plugin_dir, name="toggle_plugin")
    runner = CliRunner()

    assert runner.invoke(plugin_commands.app, ["install", str(plugin_dir)]).exit_code == 0

    disabled = runner.invoke(plugin_commands.app, ["disable", "toggle_plugin"])
    assert disabled.exit_code == 0
    assert "toggle_plugin" in disabled.output

    disabled_list = runner.invoke(plugin_commands.app, ["list", "--disabled"])
    assert disabled_list.exit_code == 0
    assert "toggle_plugin" in disabled_list.output
    assert "DISABLED" in disabled_list.output

    enabled = runner.invoke(plugin_commands.app, ["enable", "toggle_plugin"])
    assert enabled.exit_code == 0
    assert "toggle_plugin" in enabled.output

    enabled_list = runner.invoke(plugin_commands.app, ["list", "--enabled"])
    assert enabled_list.exit_code == 0
    assert "toggle_plugin" in enabled_list.output
    assert "ENABLED" in enabled_list.output


def test_plugin_uninstall_removes_state_and_directory(plugin_cli_env, tmp_path: Path):
    install_root, state_file = plugin_cli_env
    plugin_dir = tmp_path / "remove_plugin_src"
    _create_test_plugin(plugin_dir, name="remove_plugin")
    runner = CliRunner()

    assert runner.invoke(plugin_commands.app, ["install", str(plugin_dir)]).exit_code == 0

    uninstall = runner.invoke(plugin_commands.app, ["uninstall", "remove_plugin"])
    assert uninstall.exit_code == 0
    assert "remove_plugin" in uninstall.output
    assert not (install_root / "remove_plugin").exists()

    state_payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert "remove_plugin" not in state_payload.get("plugins", {})


def test_plugin_install_from_url(plugin_cli_env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plugin_dir = tmp_path / "url_plugin_src"
    cleanup_dir = tmp_path / "cleanup_url"
    cleanup_dir.mkdir(parents=True, exist_ok=True)
    _create_test_plugin(plugin_dir, name="url_plugin")

    monkeypatch.setattr(
        plugin_commands,
        "_download_and_extract_plugin_from_url",
        lambda _url: (plugin_dir, cleanup_dir),
    )

    runner = CliRunner()
    result = runner.invoke(plugin_commands.app, ["install", "https://example.com/plugin.zip"])
    assert result.exit_code == 0
    assert "url_plugin" in result.output

    listed = runner.invoke(plugin_commands.app, ["list", "--all"])
    assert listed.exit_code == 0
    assert "url_plugin" in listed.output
    assert not cleanup_dir.exists()


def test_plugin_install_from_marketplace(plugin_cli_env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plugin_dir = tmp_path / "market_plugin_src"
    cleanup_dir = tmp_path / "cleanup_market"
    cleanup_dir.mkdir(parents=True, exist_ok=True)
    _create_test_plugin(plugin_dir, name="market_plugin")

    monkeypatch.setattr(
        plugin_commands.MarketplaceClient,
        "get_plugin_details",
        lambda self, _plugin_id: {
            "plugin_id": "market-plugin",
            "name": "Market Plugin",
            "download_url": "https://marketplace.local/plugin.zip",
        },
    )
    monkeypatch.setattr(
        plugin_commands.MarketplaceClient,
        "get_plugin_versions",
        lambda self, _plugin_id: [
            {"version": "1.2.3", "download_url": "https://marketplace.local/plugin-1.2.3.zip"}
        ],
    )
    monkeypatch.setattr(
        plugin_commands,
        "_download_and_extract_plugin_from_url",
        lambda _url: (plugin_dir, cleanup_dir),
    )

    runner = CliRunner()
    result = runner.invoke(plugin_commands.app, ["install", "market-plugin", "--version", "1.2.3"])
    assert result.exit_code == 0
    assert "market_plugin" in result.output

    listed = runner.invoke(plugin_commands.app, ["list", "--all"])
    assert listed.exit_code == 0
    assert "market_plugin" in listed.output
