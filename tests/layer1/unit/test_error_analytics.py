"""Unit tests for monitoring.error_analytics."""

from vagus.monitoring.error_analytics import ErrorAnalyticsStorage, classify_error


def test_classify_error_transient():
    assert classify_error("timeout while calling upstream") == "transient"
    assert classify_error("rate_limit exceeded") == "transient"


def test_classify_error_permanent():
    assert classify_error("validation failed for payload") == "permanent"
    assert classify_error("unauthorized token") == "permanent"


def test_classify_error_infrastructure():
    assert classify_error("database is locked") == "infrastructure"
    assert classify_error("network connection reset by peer") == "infrastructure"


def test_error_analytics_aggregations(tmp_path):
    storage = ErrorAnalyticsStorage(str(tmp_path / "errors.db"))
    storage.record_error(source="api.tasks", message="timeout", error_type="TimeoutError")
    storage.record_error(source="api.tasks", message="timeout", error_type="TimeoutError")
    storage.record_error(source="router", message="validation failed", error_type="ValueError")

    rates = storage.get_error_rate_by_type(window_minutes=60)
    assert rates["total_errors"] == 3
    assert rates["counts"]["transient"] == 2
    assert rates["counts"]["permanent"] == 1

    top_sources = storage.get_top_error_sources(limit=2, window_minutes=60)
    assert top_sources[0]["source"] == "api.tasks"
    assert top_sources[0]["count"] == 2

    snapshot = storage.build_analytics_snapshot(
        window_minutes=60,
        top_sources_limit=5,
        metrics_context={"requests": 10, "cache_hit_rate_percent": 80.0},
    )
    assert "error_rate_by_type" in snapshot
    assert "top_error_sources" in snapshot
    assert "correlation" in snapshot
    assert snapshot["correlation"]["cache_hit_rate_percent"] == 80.0
