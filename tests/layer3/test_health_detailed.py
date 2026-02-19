"""Tests for detailed health checks endpoint."""

from vagus.layer3.api.health import HealthThresholds, run_detailed_health_checks


def test_health_detailed_endpoint_returns_dependency_report(client):
    response = client.get("/health/detailed")
    assert response.status_code == 200
    payload = response.json()

    assert "status" in payload
    assert "checks" in payload
    assert "database" in payload["checks"]
    assert "redis" in payload["checks"]
    assert "llm_providers" in payload["checks"]
    assert "secrets_manager" in payload["checks"]
    assert "disk_space" in payload["checks"]
    assert "memory_usage" in payload["checks"]


def test_health_check_fails_when_disk_threshold_is_too_strict(app):
    app.state.health_thresholds = HealthThresholds(
        disk_free_percent_min=101.0,
        memory_usage_percent_max=99.0,
        disk_path=".",
    )
    report = run_detailed_health_checks(app)
    assert report["checks"]["disk_space"]["status"] == "failed"
    assert report["status"] in {"failed", "degraded"}


def test_health_check_redis_is_skipped_without_config(app):
    app.state.security_settings["rate_limit"]["redis_url"] = None
    report = run_detailed_health_checks(app)
    assert report["checks"]["redis"]["status"] == "skipped"
