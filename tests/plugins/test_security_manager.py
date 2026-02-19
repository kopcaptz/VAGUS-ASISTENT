"""Tests for sandbox SecurityManager."""

from __future__ import annotations

from pathlib import Path

import pytest

from vagus.plugins.core.models import PermissionLevel, PluginPermissions
from vagus.plugins.sandbox.security_manager import SecurityManager, SecurityViolationError


def test_security_manager_allows_read_on_allowed_path(tmp_path: Path):
    read_root = tmp_path / "data"
    read_root.mkdir()
    manager = SecurityManager()
    permissions = PluginPermissions(
        level=PermissionLevel.READ,
        filesystem={"read": [str(read_root)], "write": []},
    )

    manager.check_filesystem_access(
        plugin_name="demo",
        permissions=permissions,
        path=read_root / "file.txt",
        write=False,
    )


def test_security_manager_denies_write_without_write_permission(tmp_path: Path):
    read_root = tmp_path / "data"
    read_root.mkdir()
    manager = SecurityManager()
    permissions = PluginPermissions(
        level=PermissionLevel.READ,
        filesystem={"read": [str(read_root)], "write": []},
    )

    with pytest.raises(SecurityViolationError):
        manager.check_filesystem_access(
            plugin_name="demo",
            permissions=permissions,
            path=read_root / "file.txt",
            write=True,
        )


def test_security_manager_enforces_network_whitelist():
    manager = SecurityManager()
    permissions = PluginPermissions(
        level=PermissionLevel.NETWORK,
        network=["api.openai.com"],
    )

    manager.check_network_access("demo", permissions, "api.openai.com")
    with pytest.raises(SecurityViolationError):
        manager.check_network_access("demo", permissions, "example.com")


def test_security_manager_blocks_process_creation_for_non_system():
    manager = SecurityManager()
    permissions = PluginPermissions(level=PermissionLevel.NETWORK)
    with pytest.raises(SecurityViolationError):
        manager.check_process_creation("demo", permissions)


def test_security_manager_audit_log_contains_events(tmp_path: Path):
    manager = SecurityManager()
    root = tmp_path / "data"
    root.mkdir()
    permissions = PluginPermissions(
        level=PermissionLevel.READ,
        filesystem={"read": [str(root)], "write": []},
    )

    manager.check_filesystem_access("demo", permissions, root / "ok.txt", write=False)
    with pytest.raises(SecurityViolationError):
        manager.check_network_access("demo", permissions, "api.openai.com")

    events = manager.get_audit_events("demo")
    assert len(events) >= 2
    assert any(event.allowed for event in events)
    assert any(not event.allowed for event in events)
