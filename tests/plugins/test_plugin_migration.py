"""Tests for plugin migration manager."""

from __future__ import annotations

import copy

import pytest

from vagus.plugins.backup import PluginBackupManager
from vagus.plugins.migration import PluginMigrationError, PluginMigrationManager


def test_plugin_migration_applies_registered_path(tmp_path):
    backup = PluginBackupManager(backup_root=tmp_path / "backups")
    manager = PluginMigrationManager(backup_manager=backup)
    manager.register_migration("demo", "1.0.0", "1.1.0", lambda cfg: {**cfg, "a": 1})
    manager.register_migration("demo", "1.1.0", "1.2.0", lambda cfg: {**cfg, "b": 2})

    migrated = manager.migrate_config(
        plugin_name="demo",
        current_version="1.0.0",
        target_version="1.2.0",
        config={"base": True},
    )
    assert migrated == {"base": True, "a": 1, "b": 2}


def test_plugin_migration_same_version_returns_copy(tmp_path):
    backup = PluginBackupManager(backup_root=tmp_path / "backups")
    manager = PluginMigrationManager(backup_manager=backup)
    original = {"x": 1}
    result = manager.migrate_config(
        plugin_name="demo",
        current_version="1.0.0",
        target_version="1.0.0",
        config=original,
    )
    assert result == original
    assert result is not original


def test_plugin_migration_raises_without_path(tmp_path):
    backup = PluginBackupManager(backup_root=tmp_path / "backups")
    manager = PluginMigrationManager(backup_manager=backup)
    with pytest.raises(PluginMigrationError):
        manager.migrate_config(
            plugin_name="demo",
            current_version="1.0.0",
            target_version="1.1.0",
            config={"x": 1},
        )


def test_plugin_migration_rolls_back_on_failure(tmp_path):
    backup = PluginBackupManager(backup_root=tmp_path / "backups")
    manager = PluginMigrationManager(backup_manager=backup)

    def broken(cfg):
        payload = copy.deepcopy(cfg)
        payload["x"] = 2
        raise RuntimeError("migration failed")

    manager.register_migration("demo", "1.0.0", "1.1.0", broken)
    with pytest.raises(PluginMigrationError):
        manager.migrate_config(
            plugin_name="demo",
            current_version="1.0.0",
            target_version="1.1.0",
            config={"x": 1},
        )
    rolled_back = manager.rollback("demo")
    assert rolled_back == {"x": 1}


def test_plugin_migration_updates_dependencies():
    manager = PluginMigrationManager()
    merged = manager.update_dependencies(
        current_dependencies=["a>=1.0", "b>=2.0"],
        new_dependencies=["b>=2.0", "c>=3.0"],
    )
    assert merged == ["a>=1.0", "b>=2.0", "c>=3.0"]
