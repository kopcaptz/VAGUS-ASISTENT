"""Helpers for plugin dashboard UI."""

from __future__ import annotations

from typing import Any


def summarize_installed_plugins(plugins: list[dict[str, Any]]) -> dict[str, int]:
    total = len(plugins)
    enabled = sum(1 for plugin in plugins if bool(plugin.get("enabled", False)))
    disabled = total - enabled
    with_errors = sum(1 for plugin in plugins if plugin.get("state") == "ERROR")
    return {
        "total": total,
        "enabled": enabled,
        "disabled": disabled,
        "with_errors": with_errors,
    }


def filter_marketplace_plugins(
    plugins: list[dict[str, Any]],
    *,
    query: str = "",
    category: str | None = None,
) -> list[dict[str, Any]]:
    query_lower = query.strip().lower()
    category_lower = category.strip().lower() if category else None
    filtered: list[dict[str, Any]] = []
    for plugin in plugins:
        name = str(plugin.get("name") or plugin.get("plugin_id") or "")
        description = str(plugin.get("description") or "")
        plugin_category = str(plugin.get("category") or "").lower()

        if query_lower and query_lower not in name.lower() and query_lower not in description.lower():
            continue
        if category_lower and plugin_category != category_lower:
            continue
        filtered.append(plugin)
    return filtered


def build_dependency_edges(graph: dict[str, list[str]]) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for source, targets in graph.items():
        if not targets:
            edges.append({"source": source, "target": source})
            continue
        for target in targets:
            edges.append({"source": source, "target": target})
    return edges


def format_plugin_logs(log_rows: list[dict[str, Any]], *, limit: int = 100) -> list[str]:
    prepared = []
    for row in log_rows[:limit]:
        timestamp = row.get("timestamp", "-")
        plugin_name = row.get("plugin", "unknown")
        level = row.get("level", "INFO")
        message = row.get("message", "")
        prepared.append(f"[{timestamp}] [{level}] [{plugin_name}] {message}")
    return prepared
