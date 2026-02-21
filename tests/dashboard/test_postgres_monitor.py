"""Tests for dashboard postgres_monitor utils."""

from unittest.mock import MagicMock

import pytest

try:
    from dashboard.utils.postgres_monitor import fetch_postgres_metrics
except ModuleNotFoundError:
    from utils.postgres_monitor import fetch_postgres_metrics


def test_fetch_postgres_metrics_on_success():
    mock_client = MagicMock()
    mock_client.get_monitoring_postgres.return_value = {
        "available": True,
        "backend": "postgres",
        "artifacts_count": 100,
        "relationships_count": 50,
        "query_time_ms": 12.5,
    }
    result = fetch_postgres_metrics(mock_client)
    assert result["available"] is True
    assert result["backend"] == "postgres"
    assert result["artifacts_count"] == 100
    assert result["relationships_count"] == 50
    assert result["query_time_ms"] == 12.5


def test_fetch_postgres_metrics_on_error():
    mock_client = MagicMock()
    mock_client.get_monitoring_postgres.side_effect = Exception("Connection refused")
    result = fetch_postgres_metrics(mock_client)
    assert result["available"] is False
    assert "error" in result
    assert result["artifacts_count"] == 0
    assert result["relationships_count"] == 0
