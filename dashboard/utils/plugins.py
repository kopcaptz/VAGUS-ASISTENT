"""Helpers for plugin dashboard UI."""

from __future__ import annotations

import json
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


def build_ui_form_fields(ui_schema: dict[str, Any], settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Build dynamic form field descriptors from plugin ui_schema."""
    fields: list[dict[str, Any]] = []
    properties = ui_schema.get("properties", {}) if isinstance(ui_schema, dict) else {}
    required = set(ui_schema.get("required", [])) if isinstance(ui_schema, dict) else set()

    for field_name, field_schema in properties.items():
        if not isinstance(field_schema, dict):
            continue
        field_type = str(field_schema.get("type", "string"))
        fields.append(
            {
                "name": field_name,
                "type": field_type,
                "title": field_schema.get("title", field_name),
                "description": field_schema.get("description", ""),
                "required": field_name in required,
                "default": field_schema.get("default"),
                "value": settings.get(field_name, field_schema.get("default")),
                "enum": field_schema.get("enum", []),
                "minimum": field_schema.get("minimum"),
                "maximum": field_schema.get("maximum"),
            }
        )
    return fields


def validate_plugin_settings(settings: dict[str, Any], ui_schema: dict[str, Any]) -> list[str]:
    """Validate settings dictionary against simplified json-schema subset."""
    errors: list[str] = []
    properties = ui_schema.get("properties", {}) if isinstance(ui_schema, dict) else {}
    required = set(ui_schema.get("required", [])) if isinstance(ui_schema, dict) else set()

    for required_field in required:
        if required_field not in settings or settings.get(required_field) in (None, ""):
            errors.append(f"Field '{required_field}' is required")

    for field_name, field_schema in properties.items():
        if field_name not in settings or not isinstance(field_schema, dict):
            continue
        value = settings[field_name]
        field_type = field_schema.get("type", "string")
        if field_type == "number":
            if not isinstance(value, (int, float)):
                errors.append(f"Field '{field_name}' must be a number")
                continue
            minimum = field_schema.get("minimum")
            maximum = field_schema.get("maximum")
            if minimum is not None and value < minimum:
                errors.append(f"Field '{field_name}' must be >= {minimum}")
            if maximum is not None and value > maximum:
                errors.append(f"Field '{field_name}' must be <= {maximum}")
        elif field_type == "boolean":
            if not isinstance(value, bool):
                errors.append(f"Field '{field_name}' must be boolean")
        elif field_type == "array":
            if not isinstance(value, list):
                errors.append(f"Field '{field_name}' must be an array")
        elif field_type == "object":
            if not isinstance(value, dict):
                errors.append(f"Field '{field_name}' must be an object")
        else:
            if not isinstance(value, str):
                errors.append(f"Field '{field_name}' must be a string")

        enum_values = field_schema.get("enum")
        if isinstance(enum_values, list) and enum_values and value not in enum_values:
            errors.append(f"Field '{field_name}' must be one of {enum_values}")
    return errors


def render_live_preview(settings: dict[str, Any]) -> str:
    """Build live preview JSON payload for plugin settings."""
    return json.dumps(settings, ensure_ascii=True, indent=2, sort_keys=True)
