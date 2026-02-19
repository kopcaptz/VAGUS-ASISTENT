"""Tests for performance dashboard utility functions."""

import time

from dashboard.utils.charts import (
    append_history_snapshot,
    build_performance_snapshot,
    calculate_avg_request_latency_ms,
    calculate_cache_hit_ratio,
    calculate_http_error_rate,
    parse_prometheus_samples,
)


PROMETHEUS_FIXTURE = """
# HELP http_requests_total Total number of HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",endpoint="/health",status="200"} 90
http_requests_total{method="GET",endpoint="/health",status="500"} 10
# HELP http_request_duration_seconds HTTP request duration in seconds
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_sum{method="GET",endpoint="/health"} 5
http_request_duration_seconds_count{method="GET",endpoint="/health"} 100
cache_hits_total 80
cache_misses_total 20
websocket_connections_active 4
"""


def test_parse_prometheus_samples_and_calculations():
    samples = parse_prometheus_samples(PROMETHEUS_FIXTURE)
    assert samples

    error_rate = calculate_http_error_rate(samples)
    latency_ms = calculate_avg_request_latency_ms(samples)
    cache_ratio = calculate_cache_hit_ratio(samples)

    assert round(error_rate, 2) == 10.0
    assert round(latency_ms, 2) == 50.0
    assert round(cache_ratio, 2) == 80.0


def test_build_performance_snapshot():
    status = {"layer1_stats": {"total_cost": 1.23}}
    snapshot = build_performance_snapshot(PROMETHEUS_FIXTURE, status)

    assert snapshot["request_latency_ms"] == 50.0
    assert snapshot["error_rate_percent"] == 10.0
    assert snapshot["active_connections"] == 4.0
    assert snapshot["cache_hit_ratio_percent"] == 80.0
    assert snapshot["llm_provider_cost_usd"] == 1.23


def test_append_history_snapshot_prunes_old_values():
    now = time.time()
    history = [
        {"timestamp": now - (25 * 3600), "request_latency_ms": 10},
        {"timestamp": now - 60, "request_latency_ms": 20},
    ]
    updated = append_history_snapshot(
        history,
        {"timestamp": now, "request_latency_ms": 30},
        now_ts=now,
        window_hours=24,
    )
    assert len(updated) == 2
    assert updated[0]["request_latency_ms"] == 20
    assert updated[1]["request_latency_ms"] == 30
