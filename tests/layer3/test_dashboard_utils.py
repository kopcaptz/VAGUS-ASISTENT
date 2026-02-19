"""Тесты утилит Dashboard."""

import pytest
from dashboard.utils.charts import (
    append_circuit_breaker_history,
    circuit_breaker_state_to_numeric,
    extract_error_rates,
    extract_metrics,
    flatten_circuit_breaker_history,
    format_cost,
    format_uptime,
)


def test_format_uptime_seconds():
    assert "сек" in format_uptime(30)


def test_format_uptime_minutes():
    assert "мин" in format_uptime(120)


def test_format_uptime_hours():
    assert "ч" in format_uptime(7200)


def test_format_uptime_days():
    assert "дн" in format_uptime(100000)


def test_format_cost():
    assert format_cost(0.0015) == "$0.0015"
    assert format_cost(0) == "$0.0000"


def test_extract_metrics():
    status = {
        "layer1_stats": {
            "requests": 100,
            "total_cost": 1.5,
            "cache": {"hit_rate_percent": 85.5},
        },
        "layer2_agents_count": 3,
        "active_tasks_count": 2,
        "uptime_seconds": 3600,
    }
    m = extract_metrics(status)
    assert m["agents"] == 3
    assert m["active_tasks"] == 2
    assert m["requests"] == 100
    assert m["cache_hit_rate"] == 85.5
    assert "ч" in m["uptime"]


def test_extract_metrics_empty():
    m = extract_metrics({})
    assert m["agents"] == 0
    assert m["requests"] == 0


def test_circuit_breaker_state_to_numeric():
    assert circuit_breaker_state_to_numeric("closed") == 0
    assert circuit_breaker_state_to_numeric("open") == 1
    assert circuit_breaker_state_to_numeric("half-open") == 2


def test_append_and_flatten_circuit_breaker_history():
    history = []
    history = append_circuit_breaker_history(
        history,
        {"timestamp": 100.0, "states": {"openai": "closed"}},
        now_ts=100.0,
    )
    history = append_circuit_breaker_history(
        history,
        {"timestamp": 101.0, "states": {"openai": "open", "anthropic": "half-open"}},
        now_ts=101.0,
    )
    rows = flatten_circuit_breaker_history(history)
    assert len(rows) == 3
    assert any(row["provider_id"] == "openai" and row["state_numeric"] == 1 for row in rows)
    assert any(row["provider_id"] == "anthropic" and row["state_numeric"] == 2 for row in rows)


def test_extract_error_rates():
    rates = extract_error_rates(
        {
            "error_rate_by_type": {
                "rates_percent": {"transient": 25.0, "permanent": 50.0, "infrastructure": 25.0}
            }
        }
    )
    assert rates["transient"] == 25.0
    assert rates["permanent"] == 50.0
    assert rates["infrastructure"] == 25.0
