"""Tests for memory profiler and admin endpoint."""

import time

from vagus.monitoring.memory_profiler import MemoryLeakPolicy, MemoryProfiler


def test_memory_profiler_collects_snapshot():
    profiler = MemoryProfiler()
    snapshot = profiler.collect_snapshot()
    assert "process_memory_mb" in snapshot
    assert "python_object_count" in snapshot
    assert "gc_stats" in snapshot
    assert "leak_signal" in snapshot


def test_memory_profiler_detects_growth_over_threshold(monkeypatch):
    profiler = MemoryProfiler(leak_policy=MemoryLeakPolicy(threshold_mb=100.0, window_seconds=300))
    profiler._history.append(
        {
            "monotonic_ts": time.monotonic() - 5.0,
            "process_memory_mb": 100.0,
        }
    )
    monkeypatch.setattr(profiler, "_read_process_memory_mb", lambda: 250.0)
    snapshot = profiler.collect_snapshot()
    assert snapshot["leak_signal"]["detected"] is True
    assert snapshot["leak_signal"]["growth_mb"] >= 100.0


def test_admin_memory_stats_endpoint(app, client, admin_headers):
    app.state.memory_profiler = MemoryProfiler()
    response = client.get("/api/v1/admin/memory-stats?history_limit=5", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert "current" in payload
    assert "history" in payload
    assert "leak_policy" in payload
