"""Tests for Prometheus metrics endpoint and helpers."""

from vagus.layer3.api.metrics import (
    decrement_websocket_connections,
    increment_websocket_connections,
    prometheus_metrics,
    record_cache_hit,
    record_cache_miss,
    record_llm_request,
    record_task_execution,
    set_circuit_breaker_state,
)


def test_metrics_endpoint_exposes_required_metrics(client):
    prometheus_metrics.reset()

    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text

    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body
    assert "websocket_connections_active" in body
    assert "task_execution_total" in body
    assert "llm_requests_total" in body
    assert "cache_hits_total" in body
    assert "cache_misses_total" in body
    assert "circuit_breaker_state" in body


def test_http_request_metrics_are_recorded(client):
    prometheus_metrics.reset()

    health_response = client.get("/health")
    assert health_response.status_code == 200

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    body = metrics_response.text
    assert 'http_requests_total{method="GET",endpoint="/health",status="200"}' in body


def test_manual_metric_helpers_update_exposition(client):
    prometheus_metrics.reset()

    increment_websocket_connections()
    record_task_execution("researcher", "success")
    record_llm_request("openai", "gpt-4o-mini", "success")
    record_cache_hit()
    record_cache_miss()
    set_circuit_breaker_state(2)
    decrement_websocket_connections()

    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    body = metrics_response.text

    assert 'task_execution_total{agent_type="researcher",status="success"} 1.0' in body
    assert 'llm_requests_total{provider="openai",model="gpt-4o-mini",status="success"} 1.0' in body
    assert "cache_hits_total 1.0" in body
    assert "cache_misses_total 1.0" in body
    assert "circuit_breaker_state 2.0" in body
