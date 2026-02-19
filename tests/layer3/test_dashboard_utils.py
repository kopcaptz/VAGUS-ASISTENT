"""Тесты утилит Dashboard."""

import pytest
from dashboard.utils.charts import extract_metrics, format_cost, format_uptime


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
