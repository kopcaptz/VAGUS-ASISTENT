"""Plugin configuration migration and rollback manager."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from packaging.version import Version

from ..backup import PluginBackupManager


class PluginMigrationError(RuntimeError):
    """Raised when plugin migration cannot be completed."""


@dataclass
class MigrationStep:
    plugin_name: str
    from_version: str
    to_version: str
    migrate_fn: Callable[[dict[str, Any]], dict[str, Any]]


class PluginMigrationManager:
    """Applies versioned plugin config migrations with rollback support."""

    def __init__(self, backup_manager: Optional[PluginBackupManager] = None) -> None:
        self.backup_manager = backup_manager or PluginBackupManager()
        self._steps: dict[str, list[MigrationStep]] = {}
        self._latest_backup_file: dict[str, Path] = {}

    def register_migration(
        self,
        plugin_name: str,
        from_version: str,
        to_version: str,
        migrate_fn: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        step = MigrationStep(
            plugin_name=plugin_name,
            from_version=from_version,
            to_version=to_version,
            migrate_fn=migrate_fn,
        )
        steps = self._steps.setdefault(plugin_name, [])
        steps.append(step)
        steps.sort(key=lambda item: Version(item.from_version))

    def migrate_config(
        self,
        *,
        plugin_name: str,
        current_version: str,
        target_version: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        if Version(current_version) == Version(target_version):
            return copy.deepcopy(config)

        planned_steps = self._build_migration_path(plugin_name, current_version, target_version)
        if not planned_steps:
            raise PluginMigrationError(
                f"No migration path for plugin '{plugin_name}' from {current_version} to {target_version}"
            )

        backup = self.backup_manager.backup_configuration(
            {"plugin_name": plugin_name, "version": current_version, "config": config},
            name=f"migration_{plugin_name}",
        )
        self._latest_backup_file[plugin_name] = backup

        migrated = copy.deepcopy(config)
        try:
            for step in planned_steps:
                migrated = step.migrate_fn(copy.deepcopy(migrated))
                if not isinstance(migrated, dict):
                    raise PluginMigrationError(
                        f"Migration step {step.from_version}->{step.to_version} returned invalid payload"
                    )
            return migrated
        except Exception as exc:
            restored = self.rollback(plugin_name)
            raise PluginMigrationError(
                f"Migration failed for plugin '{plugin_name}', rollback applied: {exc}. Restored={bool(restored)}"
            ) from exc

    def rollback(self, plugin_name: str) -> Optional[dict[str, Any]]:
        backup_file = self._latest_backup_file.get(plugin_name)
        if backup_file is None:
            return None
        payload = self.backup_manager.restore_configuration(backup_file)
        plugin_payload = payload.get("config", payload)
        if isinstance(plugin_payload, dict) and "config" in plugin_payload:
            inner = plugin_payload.get("config")
            if isinstance(inner, dict):
                return inner
        return plugin_payload if isinstance(plugin_payload, dict) else None

    def update_dependencies(
        self,
        *,
        current_dependencies: list[str],
        new_dependencies: list[str],
    ) -> list[str]:
        merged = list(current_dependencies)
        for dependency in new_dependencies:
            if dependency not in merged:
                merged.append(dependency)
        return merged

    def _build_migration_path(
        self,
        plugin_name: str,
        current_version: str,
        target_version: str,
    ) -> list[MigrationStep]:
        steps = self._steps.get(plugin_name, [])
        current = Version(current_version)
        target = Version(target_version)
        if current > target:
            raise PluginMigrationError("Downgrade migrations are not supported")

        path: list[MigrationStep] = []
        while current < target:
            candidate = None
            for step in steps:
                if Version(step.from_version) == current and Version(step.to_version) <= target:
                    candidate = step
                    break
            if candidate is None:
                return []
            path.append(candidate)
            current = Version(candidate.to_version)
        return path
