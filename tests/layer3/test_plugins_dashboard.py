"""Tests for plugin dashboard helper utilities."""

from __future__ import annotations

from dashboard.utils.plugins import (
    build_dependency_edges,
    filter_marketplace_plugins,
    format_plugin_logs,
    summarize_installed_plugins,
)


def test_summarize_installed_plugins():
    summary = summarize_installed_plugins(
        [
            {"name": "a", "enabled": True, "state": "ENABLED"},
            {"name": "b", "enabled": False, "state": "DISABLED"},
            {"name": "c", "enabled": True, "state": "ERROR"},
        ]
    )
    assert summary["total"] == 3
    assert summary["enabled"] == 2
    assert summary["disabled"] == 1
    assert summary["with_errors"] == 1


def test_summarize_installed_plugins_uses_status_field():
    summary = summarize_installed_plugins(
        [
            {"name": "a", "enabled": True, "status": "ENABLED"},
            {"name": "b", "enabled": False, "status": "ERROR"},
        ]
    )
    assert summary["total"] == 2
    assert summary["with_errors"] == 1


def test_filter_marketplace_plugins_by_query_and_category():
    plugins = [
        {"plugin_id": "alpha", "name": "Alpha Tool", "description": "utilities", "category": "utility"},
        {"plugin_id": "beta", "name": "Beta AI", "description": "analysis", "category": "analytics"},
    ]

    filtered = filter_marketplace_plugins(plugins, query="alpha", category="utility")
    assert len(filtered) == 1
    assert filtered[0]["plugin_id"] == "alpha"


def test_build_dependency_edges():
    graph = {"a": ["b", "c"], "b": [], "c": []}
    edges = build_dependency_edges(graph)
    assert {"source": "a", "target": "b"} in edges
    assert {"source": "a", "target": "c"} in edges
    assert {"source": "b", "target": "b"} in edges


def test_format_plugin_logs_limit():
    rows = [
        {"timestamp": "t1", "plugin": "p1", "level": "INFO", "message": "m1"},
        {"timestamp": "t2", "plugin": "p2", "level": "ERROR", "message": "m2"},
    ]
    formatted = format_plugin_logs(rows, limit=1)
    assert len(formatted) == 1
    assert "[INFO]" in formatted[0]
