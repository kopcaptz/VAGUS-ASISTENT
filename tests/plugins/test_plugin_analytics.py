"""Tests for plugin analytics module."""

from __future__ import annotations

from vagus.plugins.analytics import PluginAnalytics


def test_plugin_analytics_records_calls_and_metrics():
    analytics = PluginAnalytics()
    analytics.record_call("plugin_a", execution_time_seconds=0.5, success=True)
    analytics.record_call("plugin_a", execution_time_seconds=1.5, success=False)

    metrics = analytics.get_metrics("plugin_a")
    assert metrics.calls == 2
    assert metrics.successes == 1
    assert metrics.failures == 1
    assert metrics.average_execution_time_seconds == 1.0


def test_plugin_analytics_popularity_ranking():
    analytics = PluginAnalytics()
    analytics.record_call("plugin_a", execution_time_seconds=0.1, success=True)
    analytics.record_call("plugin_b", execution_time_seconds=0.1, success=True)
    analytics.record_call("plugin_b", execution_time_seconds=0.2, success=True)

    ranking = analytics.get_popularity(limit=2)
    assert ranking[0]["plugin_name"] == "plugin_b"
    assert ranking[1]["plugin_name"] == "plugin_a"


def test_plugin_analytics_dashboard_data():
    analytics = PluginAnalytics()
    analytics.record_call("plugin_a", execution_time_seconds=0.2, success=True)
    analytics.record_call("plugin_b", execution_time_seconds=0.3, success=False)

    dashboard = analytics.get_dashboard_data()
    assert dashboard["summary"]["total_plugins"] == 2
    assert dashboard["summary"]["total_calls"] == 2
    assert dashboard["summary"]["success_rate"] == 0.5


def test_plugin_analytics_recommendations_use_top_categories():
    analytics = PluginAnalytics()
    analytics.set_plugin_category("plugin_a", "analytics")
    analytics.record_call("plugin_a", execution_time_seconds=0.2, success=True)
    analytics.record_call("plugin_a", execution_time_seconds=0.3, success=True)

    recommendations = analytics.recommend_plugins(
        installed_plugins=["plugin_a"],
        marketplace_plugins=[
            {"plugin_id": "plugin_b", "category": "analytics", "avg_rating": 4.0, "review_count": 10},
            {"plugin_id": "plugin_c", "category": "utility", "avg_rating": 4.9, "review_count": 1},
        ],
        limit=2,
    )
    assert recommendations[0]["plugin_id"] == "plugin_b"


def test_plugin_analytics_skips_installed_plugins_in_recommendations():
    analytics = PluginAnalytics()
    recommendations = analytics.recommend_plugins(
        installed_plugins=["plugin_x"],
        marketplace_plugins=[
            {"plugin_id": "plugin_x", "category": "analytics", "avg_rating": 5.0, "review_count": 100},
            {"plugin_id": "plugin_y", "category": "analytics", "avg_rating": 3.0, "review_count": 1},
        ],
    )
    assert all(item["plugin_id"] != "plugin_x" for item in recommendations)
