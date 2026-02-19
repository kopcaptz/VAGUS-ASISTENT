"""Secure plugin example."""

from __future__ import annotations


class SecurePlugin:
    """Example plugin that only performs safe task preprocessing."""

    def pre_task_execution(self, task: dict) -> dict:
        updated = dict(task)
        metadata = dict(updated.get("metadata", {}))
        metadata["secure_plugin_checked"] = True
        updated["metadata"] = metadata
        return updated
