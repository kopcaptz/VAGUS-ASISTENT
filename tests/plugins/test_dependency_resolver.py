"""Tests for plugin dependency resolver."""

from __future__ import annotations

import pytest

from vagus.plugins.dependencies import DependencyResolutionError, PluginDependencyResolver


def test_dependency_resolver_resolves_topological_order():
    resolver = PluginDependencyResolver()
    resolver.add_plugin("core", "1.0.0", [])
    resolver.add_plugin("analytics", "1.0.0", ["core>=1.0.0"])
    resolver.add_plugin("ui", "1.0.0", ["analytics>=1.0.0"])

    order = resolver.resolve(["ui"])
    assert order == ["core", "analytics", "ui"]


def test_dependency_resolver_detects_cycle():
    resolver = PluginDependencyResolver()
    resolver.add_plugin("a", "1.0.0", ["b>=1.0.0"])
    resolver.add_plugin("b", "1.0.0", ["a>=1.0.0"])

    with pytest.raises(DependencyResolutionError):
        resolver.resolve(["a"])


def test_dependency_resolver_detects_conflicts():
    resolver = PluginDependencyResolver()
    resolver.add_plugin("base", "1.5.0", [])
    resolver.add_plugin("plugin_x", "1.0.0", ["base>=1.0.0,<2.0.0"])
    resolver.add_plugin("plugin_y", "1.0.0", ["base>=2.0.0"])

    conflicts = resolver.detect_conflicts()
    assert "base" in conflicts


def test_dependency_resolver_install_missing_dependencies():
    resolver = PluginDependencyResolver()
    resolver.add_plugin("plugin_a", "1.0.0", ["plugin_b>=1.2.0"])

    installed = resolver.install_missing(
        ["plugin_a"],
        installer=lambda name, spec: "1.2.3" if name == "plugin_b" else "1.0.0",
    )
    assert installed == ["plugin_b"]
    assert resolver.resolve(["plugin_a"]) == ["plugin_b", "plugin_a"]


def test_dependency_resolver_visualization_format():
    resolver = PluginDependencyResolver()
    resolver.add_plugin("a", "1.0.0", ["b>=1.0.0"])
    resolver.add_plugin("b", "1.0.0", [])

    dot = resolver.visualize_graph()
    assert "digraph plugin_dependencies" in dot
    assert '"a" -> "b"' in dot


def test_dependency_resolver_invalid_specifier_raises():
    resolver = PluginDependencyResolver()
    with pytest.raises(DependencyResolutionError):
        resolver.parse_dependency("plugin_a=>=1.0.0")
