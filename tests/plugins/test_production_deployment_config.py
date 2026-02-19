"""Tests for production deployment plugin-related compose and monitoring config."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_docker_compose_contains_marketplace_and_prometheus_services():
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose.get("services", {})
    assert "marketplace" in services
    assert "prometheus" in services


def test_docker_compose_api_includes_plugin_production_env():
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    api_service = compose["services"]["api"]
    env_values = set(api_service.get("environment", []))
    assert "VAGUS_PLUGINS_ENABLED=true" in env_values
    assert any(item.startswith("VAGUS_PLUGINS_REQUIRE_SIGNATURES=") for item in env_values)


def test_prometheus_scrapes_marketplace_metrics():
    prometheus_path = Path(__file__).resolve().parents[2] / "monitoring" / "prometheus.yml"
    prometheus = yaml.safe_load(prometheus_path.read_text(encoding="utf-8"))
    scrape_configs = prometheus.get("scrape_configs", [])
    marketplace_job = next(
        (item for item in scrape_configs if item.get("job_name") == "vagus-marketplace"),
        None,
    )
    assert marketplace_job is not None
    targets = marketplace_job.get("static_configs", [])[0].get("targets", [])
    assert "marketplace:9000" in targets
