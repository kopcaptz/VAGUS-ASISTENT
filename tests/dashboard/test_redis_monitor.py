"""Tests for dashboard redis_monitor utils."""

from unittest.mock import MagicMock

import pytest

# Import after path setup - use try/except for package vs standalone
try:
    from dashboard.utils.redis_monitor import fetch_redis_metrics
except ModuleNotFoundError:
    from utils.redis_monitor import fetch_redis_metrics


def test_fetch_redis_metrics_on_success():
    mock_client = MagicMock()
    mock_client.get_monitoring_redis.return_value = {
        "available": True,
        "stream_name": "vagus:events:stream",
        "consumer_groups": [
            {"name": "memory_consolidation", "pending": 0, "consumers": 1, "last_delivered_id": "0-0"},
            {"name": "synaptic_training", "pending": 2, "consumers": 1, "last_delivered_id": "123-0"},
        ],
        "dlq_count": 0,
    }
    result = fetch_redis_metrics(mock_client)
    assert result["available"] is True
    assert result["stream_name"] == "vagus:events:stream"
    assert len(result["consumer_groups"]) == 2
    assert result["dlq_count"] == 0


def test_fetch_redis_metrics_on_error():
    mock_client = MagicMock()
    mock_client.get_monitoring_redis.side_effect = ConnectionError("API unavailable")
    result = fetch_redis_metrics(mock_client)
    assert result["available"] is False
    assert "error" in result
    assert "API unavailable" in result["error"]
    assert result.get("consumer_groups", []) == []


def test_fetch_redis_metrics_returns_dlq_count():
    mock_client = MagicMock()
    mock_client.get_monitoring_redis.return_value = {"available": True, "dlq_count": 5}
    result = fetch_redis_metrics(mock_client)
    assert result["dlq_count"] == 5
