"""Tests for plugin performance optimizer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vagus.plugins.performance import PluginPerformanceOptimizer
from vagus.plugins.registry import PluginRegistry


def _write_perf_plugin(plugin_dir: Path, *, name: str = "perf_plugin") -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": "1.0.0",
        "author": "tests",
        "description": "performance plugin",
        "dependencies": [],
        "python_version": ">=3.10",
        "vagus_version": ">=0.1.0",
        "entry_point": "plugin:Plugin",
        "hooks": [],
        "permissions": [],
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "plugin.py").write_text(
        "counter = 0\n"
        "class Plugin:\n"
        "    def compute(self, value):\n"
        "        global counter\n"
        "        counter += 1\n"
        "        return f'{counter}:{value}'\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_performance_optimizer_lazy_loading(tmp_path: Path):
    registry = PluginRegistry()
    registry.clear()
    plugin_dir = tmp_path / "perf_plugin"
    _write_perf_plugin(plugin_dir)

    optimizer = PluginPerformanceOptimizer(registry=registry)
    optimizer.register_lazy_plugin("perf_plugin", str(plugin_dir))
    plugin = optimizer.get_plugin("perf_plugin")
    assert plugin.name == "perf_plugin"


@pytest.mark.asyncio
async def test_performance_optimizer_result_cache(tmp_path: Path):
    registry = PluginRegistry()
    registry.clear()
    plugin_dir = tmp_path / "perf_plugin_cache"
    _write_perf_plugin(plugin_dir, name="perf_plugin_cache")

    optimizer = PluginPerformanceOptimizer(registry=registry, default_cache_ttl_seconds=120)
    optimizer.register_lazy_plugin("perf_plugin_cache", str(plugin_dir))

    first = await optimizer.execute_with_cache("perf_plugin_cache", "compute", "X")
    second = await optimizer.execute_with_cache("perf_plugin_cache", "compute", "X")
    third = await optimizer.execute_with_cache("perf_plugin_cache", "compute", "Y")

    assert first == second
    assert third != first


@pytest.mark.asyncio
async def test_performance_optimizer_parallel_execution(tmp_path: Path):
    registry = PluginRegistry()
    registry.clear()
    plugin_dir = tmp_path / "perf_plugin_parallel"
    _write_perf_plugin(plugin_dir, name="perf_plugin_parallel")

    optimizer = PluginPerformanceOptimizer(registry=registry)
    optimizer.register_lazy_plugin("perf_plugin_parallel", str(plugin_dir))

    results = await optimizer.execute_parallel(
        [
            {"plugin_name": "perf_plugin_parallel", "callback_name": "compute", "args": ["A"]},
            {"plugin_name": "perf_plugin_parallel", "callback_name": "compute", "args": ["B"]},
            {"plugin_name": "perf_plugin_parallel", "callback_name": "compute", "args": ["C"]},
        ],
        max_concurrency=2,
    )
    assert len(results) == 3
    assert all(":" in value for value in results)


@pytest.mark.asyncio
async def test_performance_optimizer_memory_optimization_prunes_cache(tmp_path: Path):
    registry = PluginRegistry()
    registry.clear()
    plugin_dir = tmp_path / "perf_plugin_prune"
    _write_perf_plugin(plugin_dir, name="perf_plugin_prune")

    optimizer = PluginPerformanceOptimizer(registry=registry, default_cache_ttl_seconds=120)
    optimizer.register_lazy_plugin("perf_plugin_prune", str(plugin_dir))
    for index in range(6):
        await optimizer.execute_with_cache("perf_plugin_prune", "compute", index)
    assert optimizer.cache_size() >= 6

    remaining = optimizer.optimize_memory(max_cache_entries=2)
    assert remaining <= 2


def test_performance_optimizer_clear_cache():
    optimizer = PluginPerformanceOptimizer()
    optimizer._cache_set("k", "v", ttl_seconds=60)  # pylint: disable=protected-access
    assert optimizer.cache_size() == 1
    optimizer.clear_cache()
    assert optimizer.cache_size() == 0
