"""Unit-тесты мониторинга: MetricsStorage и MonitoringService."""

from __future__ import annotations

import sqlite3

import pytest

from vagus.layer1.monitoring.metrics_storage import MetricsStorage
from vagus.layer1.monitoring.monitoring_service import MonitoringService


def test_metrics_storage_insert_get_stats_and_cleanup(tmp_path):
    db_path = tmp_path / "metrics.db"
    storage = MetricsStorage(str(db_path))

    storage.insert(
        trace_id="t1",
        provider="openai",
        model="gpt-4o-mini",
        ttft_ms=10,
        e2e_ms=20,
        cost_usd=0.1,
        success=True,
    )
    storage.insert(
        trace_id="t2",
        provider="openai",
        model="gpt-4o-mini",
        ttft_ms=12,
        e2e_ms=25,
        cost_usd=0.2,
        success=False,
        error_type="RuntimeError",
    )

    stats = storage.get_stats()
    assert stats["total_requests"] == 2
    assert stats["success_count"] == 1
    assert stats["failure_count"] == 1
    assert stats["total_cost_usd"] == 0.3

    provider_stats = storage.get_stats(provider="openai")
    assert provider_stats["total_requests"] == 2

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE request_metrics SET timestamp = ? WHERE trace_id = ?",
            ("2000-01-01T00:00:00+00:00", "t1"),
        )
        conn.commit()

    deleted = storage.cleanup_old(retention_days=30)
    assert deleted >= 1
    assert isinstance(MetricsStorage.generate_trace_id(), str)


@pytest.mark.asyncio
async def test_monitoring_service_track_request_context(tmp_path):
    service = MonitoringService(db_path=str(tmp_path / "monitoring.db"), retention_days=30)

    async with service.track_request("trace-ctx") as ctx:
        service.latency_tracker.record_ttft(ctx["latency_ctx"], 3.5)
        ctx["record_complete"](
            provider="openai",
            model="gpt-4o-mini",
            success=True,
            cost_usd=0.05,
        )

    stats = service.get_stats()
    assert stats["total_requests"] == 1
    assert stats["success_count"] == 1
