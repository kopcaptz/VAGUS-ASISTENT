"""Tests for performance benchmarking helpers."""

import pytest

from vagus.benchmarking.performance_benchmark import (
    PerformanceBenchmarkRunner,
    auto_run_if_sources_changed,
)
from vagus.layer1.cache.cache_service import CacheService
from vagus.layer1.monitoring.metrics_storage import MetricsStorage


class _FakeProvider:
    name = "fake"
    model = "fake-model"

    async def request(self, prompt: str, stream: bool = False, **kwargs):
        _ = (prompt, stream, kwargs)
        yield {"content": "ok", "done": True}


class _FakeOrchestrator:
    async def execute_task(self, task_id: str, prompt: str, task_type: str = "default", metadata=None):
        _ = (task_id, prompt, task_type, metadata)
        return {"success": True}


@pytest.mark.asyncio
async def test_performance_benchmark_runner_scenarios(tmp_path):
    runner = PerformanceBenchmarkRunner(output_dir=str(tmp_path))
    provider_result = await runner.benchmark_provider_latency(
        provider=_FakeProvider(),
        prompt="hello",
        iterations=2,
    )
    assert provider_result.name == "provider_latency"
    assert provider_result.iterations == 2

    orchestrator_result = await runner.benchmark_agent_execution(
        orchestrator=_FakeOrchestrator(),
        iterations=2,
    )
    assert orchestrator_result.name == "agent_execution"

    cache = CacheService(ttl_seconds=60, max_size_mb=1)
    cache_result = await runner.benchmark_cache_hit_miss(cache_service=cache, iterations=2)
    assert cache_result.name == "cache_hit_miss"

    storage = MetricsStorage(str(tmp_path / "metrics.db"))
    storage.insert(trace_id="t1", provider="openai", model="gpt-4o", success=True, e2e_ms=12.0)
    db_result = runner.benchmark_database_queries(metrics_storage=storage, iterations=2)
    assert db_result.name == "database_queries"

    saved_path = runner.save_results(
        suite_name="test_suite",
        scenario_results=[provider_result, orchestrator_result, cache_result, db_result],
    )
    assert saved_path.exists()


@pytest.mark.asyncio
async def test_auto_run_if_sources_changed(tmp_path):
    source_file = tmp_path / "sample.py"
    source_file.write_text("x = 1\n", encoding="utf-8")
    state_file = tmp_path / ".benchmark_state.json"

    async def _benchmark():
        return {"status": "ok"}

    first = await auto_run_if_sources_changed(
        source_paths=[str(source_file)],
        state_file=str(state_file),
        benchmark_coro=_benchmark,
    )
    assert first["executed"] is True

    second = await auto_run_if_sources_changed(
        source_paths=[str(source_file)],
        state_file=str(state_file),
        benchmark_coro=_benchmark,
    )
    assert second["executed"] is False


def test_compare_results_reports_delta():
    current = {
        "scenarios": [
            {"name": "provider_latency", "avg_ms": 120.0},
        ]
    }
    baseline = {
        "scenarios": [
            {"name": "provider_latency", "avg_ms": 100.0},
        ]
    }
    comparison = PerformanceBenchmarkRunner.compare_results(current, baseline)
    assert comparison["provider_latency"]["delta_ms"] == 20.0
    assert comparison["provider_latency"]["regression"] is True
