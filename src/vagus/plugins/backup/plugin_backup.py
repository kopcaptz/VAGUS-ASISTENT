"""Backup and restore tools for plugins and plugin configurations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any
import zipfile


class PluginBackupError(RuntimeError):
    """Raised when plugin backup/restore operation fails."""


class PluginBackupManager:
    """Handles plugin config backups and plugin export/import archives."""

    def __init__(self, backup_root: str | Path = ".vagus/plugin_backups") -> None:
        self.backup_root = Path(backup_root).expanduser().resolve()
        self.backup_root.mkdir(parents=True, exist_ok=True)

    def backup_configuration(
        self,
        config: dict[str, Any],
        *,
        name: str = "plugins_config",
    ) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{name}_{timestamp}.json"
        backup_path = self.backup_root / filename
        payload = {
            "version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "config": config,
        }
        backup_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        return backup_path

    def restore_configuration(self, backup_file: str | Path) -> dict[str, Any]:
        backup_path = Path(backup_file).expanduser().resolve()
        if not backup_path.exists():
            raise PluginBackupError(f"Backup file not found: {backup_path}")
        payload = json.loads(backup_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "config" not in payload:
            raise PluginBackupError(f"Invalid backup payload in file: {backup_path}")
        return dict(payload["config"])

    def export_plugins(self, plugin_directories: list[str | Path], archive_path: str | Path) -> Path:
        archive = Path(archive_path).expanduser().resolve()
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for directory in plugin_directories:
                plugin_dir = Path(directory).expanduser().resolve()
                if not plugin_dir.exists():
                    raise PluginBackupError(f"Plugin directory not found: {plugin_dir}")
                for file in plugin_dir.rglob("*"):
                    if file.is_dir():
                        continue
                    arcname = str(Path(plugin_dir.name) / file.relative_to(plugin_dir))
                    zip_file.write(file, arcname=arcname)
        return archive

    def import_plugins(self, archive_path: str | Path, target_directory: str | Path) -> list[Path]:
        archive = Path(archive_path).expanduser().resolve()
        if not archive.exists():
            raise PluginBackupError(f"Archive not found: {archive}")

        target_dir = Path(target_directory).expanduser().resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, mode="r") as zip_file:
            zip_file.extractall(target_dir)

        imported = sorted(path for path in target_dir.iterdir() if path.is_dir())
        return imported

    def migrate_plugins(self, source_directory: str | Path, target_directory: str | Path) -> list[Path]:
        source_dir = Path(source_directory).expanduser().resolve()
        target_dir = Path(target_directory).expanduser().resolve()
        if not source_dir.exists():
            raise PluginBackupError(f"Source directory not found: {source_dir}")
        target_dir.mkdir(parents=True, exist_ok=True)

        migrated: list[Path] = []
        for plugin_dir in source_dir.iterdir():
            if not plugin_dir.is_dir():
                continue
            destination = target_dir / plugin_dir.name
            shutil.copytree(plugin_dir, destination, dirs_exist_ok=True)
            migrated.append(destination)
        return migrated

    def list_backups(self) -> list[Path]:
        return sorted(self.backup_root.glob("*.json"), reverse=True)
