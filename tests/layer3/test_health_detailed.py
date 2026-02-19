"""Tests for detailed health checks endpoint."""

from vagus.layer3.api.health import (
    HealthThresholds,
    load_health_thresholds,
    run_detailed_health_checks,
)


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


def test_load_health_thresholds_from_config():
    cfg = {
        "monitoring": {
            "health": {
                "thresholds": {
                    "disk_free_percent_min": 12.5,
                    "memory_usage_percent_max": 85.0,
                    "check_timeout_seconds": 3.5,
                    "disk_path": "/tmp",
                }
            }
        }
    }
    thresholds = load_health_thresholds(cfg)
    assert thresholds.disk_free_percent_min == 12.5
    assert thresholds.memory_usage_percent_max == 85.0
    assert thresholds.check_timeout_seconds == 3.5
    assert thresholds.disk_path == "/tmp"


def test_health_check_reports_vault_config_error(app):
    app.state.secrets_settings = {"backend": "vault", "vault_addr": "http://localhost:8200"}
    report = run_detailed_health_checks(app)
    assert report["checks"]["secrets_manager"]["status"] == "failed"


def test_health_check_can_fail_on_memory_threshold(app):
    app.state.health_thresholds = HealthThresholds(
        disk_free_percent_min=0.0,
        memory_usage_percent_max=0.0,
        disk_path=".",
    )
    report = run_detailed_health_checks(app)
    assert report["checks"]["memory_usage"]["status"] in {"failed", "degraded"}
