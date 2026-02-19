"""Tests for plugin backup and restore tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vagus.plugins.backup import PluginBackupError, PluginBackupManager


def _create_plugin_dir(root: Path, name: str) -> Path:
    plugin_dir = root / name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "manifest.json").write_text(
        json.dumps({"name": name, "version": "1.0.0"}),
        encoding="utf-8",
    )
    (plugin_dir / "plugin.py").write_text("class Plugin: pass\n", encoding="utf-8")
    return plugin_dir


def test_backup_and_restore_configuration(tmp_path: Path):
    manager = PluginBackupManager(backup_root=tmp_path / "backups")
    backup_file = manager.backup_configuration({"enabled": ["a", "b"]})
    restored = manager.restore_configuration(backup_file)
    assert restored["enabled"] == ["a", "b"]


def test_backup_manager_lists_backups(tmp_path: Path):
    manager = PluginBackupManager(backup_root=tmp_path / "backups")
    manager.backup_configuration({"x": 1}, name="cfg")
    manager.backup_configuration({"x": 2}, name="cfg")
    backups = manager.list_backups()
    assert len(backups) == 2


def test_export_and_import_plugins(tmp_path: Path):
    source_root = tmp_path / "plugins"
    source_root.mkdir()
    plugin_a = _create_plugin_dir(source_root, "plugin_a")
    plugin_b = _create_plugin_dir(source_root, "plugin_b")

    manager = PluginBackupManager(backup_root=tmp_path / "backups")
    archive = manager.export_plugins([plugin_a, plugin_b], tmp_path / "exports" / "plugins.zip")
    imported = manager.import_plugins(archive, tmp_path / "restored")
    names = sorted(path.name for path in imported)
    assert names == ["plugin_a", "plugin_b"]


def test_migrate_plugins_between_instances(tmp_path: Path):
    source = tmp_path / "instance_a"
    target = tmp_path / "instance_b"
    source.mkdir()
    _create_plugin_dir(source, "plugin_c")

    manager = PluginBackupManager(backup_root=tmp_path / "backups")
    migrated = manager.migrate_plugins(source, target)
    assert len(migrated) == 1
    assert (target / "plugin_c" / "manifest.json").exists()


def test_restore_configuration_missing_file_raises(tmp_path: Path):
    manager = PluginBackupManager(backup_root=tmp_path / "backups")
    with pytest.raises(PluginBackupError):
        manager.restore_configuration(tmp_path / "missing.json")
