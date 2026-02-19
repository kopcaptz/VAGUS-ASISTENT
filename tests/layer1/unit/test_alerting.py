"""Unit tests for alerting service."""

from pathlib import Path

from vagus.monitoring.alerting import (
    AlertingConfig,
    AlertSnapshot,
    AlertingService,
    load_alerting_config_from_yaml,
)


def test_load_alerting_config_from_yaml(tmp_path: Path):
    config_file = tmp_path / "alerting.yaml"
    config_file.write_text(
        """
rules:
  high_error_rate_percent_5m: 7
  high_latency_p95_seconds: 3
  circuit_breaker_open_minutes: 4
  disk_free_percent_min: 15
channels:
  telegram:
    enabled: false
  email:
    enabled: false
  webhook:
    enabled: false
""".strip(),
        encoding="utf-8",
    )

    config = load_alerting_config_from_yaml(str(config_file))
    assert config.rules.high_error_rate_percent_5m == 7
    assert config.rules.high_latency_p95_seconds == 3
    assert config.rules.circuit_breaker_open_minutes == 4
    assert config.rules.disk_free_percent_min == 15


def test_evaluate_alert_rules_triggers_expected_alerts():
    snapshot = AlertSnapshot(
        error_rate_percent_5m=10.0,
        latency_p95_seconds=8.0,
        circuit_breaker_open_minutes=8.0,
        disk_free_percent=5.0,
        llm_providers={"openai": True, "anthropic": False},
    )
    service = AlertingService(AlertingConfig())
    alerts = service.evaluate(snapshot)
    rules = {alert.rule for alert in alerts}

    assert "high_error_rate" in rules
    assert "high_latency" in rules
    assert "circuit_breaker_open_too_long" in rules
    assert "low_disk_space" in rules
    assert "llm_provider_down" in rules


def test_notify_collects_errors_for_misconfigured_channels(tmp_path: Path):
    cfg = tmp_path / "alerting.yaml"
    cfg.write_text(
        """
channels:
  telegram:
    enabled: true
  email:
    enabled: true
  webhook:
    enabled: true
""".strip(),
        encoding="utf-8",
    )
    service = AlertingService.from_yaml(str(cfg))
    snapshot = AlertSnapshot(
        error_rate_percent_5m=99.0,
        latency_p95_seconds=9.0,
        circuit_breaker_open_minutes=9.0,
        disk_free_percent=1.0,
        llm_providers={"openai": False},
    )
    alerts = service.evaluate(snapshot)
    result = service.notify(alerts)
    assert result["sent"] == 0
    assert result["errors"]


def test_evaluate_returns_no_alerts_for_healthy_snapshot():
    service = AlertingService(AlertingConfig())
    snapshot = AlertSnapshot(
        error_rate_percent_5m=0.1,
        latency_p95_seconds=0.2,
        circuit_breaker_open_minutes=0.0,
        disk_free_percent=90.0,
        llm_providers={"openai": True, "anthropic": True},
    )
    alerts = service.evaluate(snapshot)
    assert alerts == []


def test_notify_returns_zero_for_empty_alert_list():
    service = AlertingService(AlertingConfig())
    result = service.notify([])
    assert result["sent"] == 0
    assert result["errors"] == []


def test_load_config_parses_string_booleans_and_numbers(tmp_path: Path):
    cfg = tmp_path / "alerting.yaml"
    cfg.write_text(
        """
channels:
  telegram:
    enabled: "true"
    bot_token: "abc"
    chat_id: "1"
  email:
    enabled: "false"
    smtp_port: "2525"
  webhook:
    enabled: "true"
    url: "https://example.com"
    timeout_seconds: "9"
""".strip(),
        encoding="utf-8",
    )
    config = load_alerting_config_from_yaml(str(cfg))
    assert config.telegram.enabled is True
    assert config.email.enabled is False
    assert config.email.smtp_port == 2525
    assert config.webhook.enabled is True
    assert config.webhook.timeout_seconds == 9.0
