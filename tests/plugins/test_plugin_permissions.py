"""Tests for PluginPermissions model and runtime checks."""

from __future__ import annotations

from pathlib import Path

from vagus.plugins.core.models import PermissionLevel, PluginPermissions


def test_plugin_permissions_path_checks(tmp_path: Path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    nested = allowed / "nested"
    nested.mkdir()
    forbidden = tmp_path / "forbidden"
    forbidden.mkdir()

    permissions = PluginPermissions(
        level=PermissionLevel.WRITE,
        filesystem={"read": [str(allowed)], "write": [str(allowed)]},
    )

    assert permissions.can_read_path(nested / "file.txt") is True
    assert permissions.can_write_path(nested / "file.txt") is True
    assert permissions.can_read_path(forbidden / "x.txt") is False
    assert permissions.can_write_path(forbidden / "x.txt") is False


def test_plugin_permissions_network_checks():
    permissions = PluginPermissions(
        level=PermissionLevel.NETWORK,
        network=["api.openai.com"],
    )
    assert permissions.can_access_domain("api.openai.com") is True
    assert permissions.can_access_domain("sub.api.openai.com") is True
    assert permissions.can_access_domain("example.com") is False


def test_plugin_permissions_env_checks():
    permissions = PluginPermissions(
        level=PermissionLevel.READ,
        environment_variables=["ALLOWED_TOKEN"],
    )
    assert permissions.can_access_env_var("ALLOWED_TOKEN") is True
    assert permissions.can_access_env_var("OTHER_TOKEN") is False


def test_plugin_permissions_none_level_blocks_all(tmp_path: Path):
    permissions = PluginPermissions(level=PermissionLevel.NONE)
    assert permissions.can_read_path(tmp_path / "x.txt") is False
    assert permissions.can_write_path(tmp_path / "x.txt") is False
    assert permissions.can_access_domain("api.openai.com") is False
    assert permissions.can_access_env_var("HOME") is False
