"""Tests for Prometheus metrics endpoint and helpers."""

from vagus.layer3.api.metrics import (
    decrement_websocket_connections,
    increment_websocket_connections,
    observe_http_request,
    prometheus_metrics,
    record_cache_hit,
    record_cache_miss,
    record_llm_request,
    record_task_execution,
    set_circuit_breaker_state,
    update_circuit_breaker_state_from_router,
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


def test_circuit_breaker_state_is_clamped_low():
    prometheus_metrics.reset()
    set_circuit_breaker_state(-1)
    body = prometheus_metrics.render()
    assert "circuit_breaker_state 0.0" in body


def test_circuit_breaker_state_is_clamped_high():
    prometheus_metrics.reset()
    set_circuit_breaker_state(99)
    body = prometheus_metrics.render()
    assert "circuit_breaker_state 2.0" in body


def test_update_circuit_breaker_state_from_router_uses_highest_state():
    prometheus_metrics.reset()

    class _State:
        def __init__(self, name):
            self.name = name

    class _Breaker:
        def __init__(self, state_name):
            self.state = _State(state_name)

    class _FallbackHandler:
        _circuit_breakers = {
            "openai": _Breaker("CLOSED"),
            "anthropic": _Breaker("HALF_OPEN"),
        }

    class _Router:
        fallback_handler = _FallbackHandler()

    update_circuit_breaker_state_from_router(_Router())
    assert "circuit_breaker_state 2.0" in prometheus_metrics.render()


def test_observe_http_request_updates_histogram_and_counter():
    prometheus_metrics.reset()
    observe_http_request("GET", "/sample", 200, 0.2)
    rendered = prometheus_metrics.render()
    assert 'http_requests_total{method="GET",endpoint="/sample",status="200"} 1.0' in rendered
    assert 'http_request_duration_seconds_count{method="GET",endpoint="/sample"} 1.0' in rendered


def test_http_metrics_capture_404_endpoint(client):
    prometheus_metrics.reset()
    resp = client.get("/api/v1/nonexistent")
    assert resp.status_code in (404, 405)
    body = client.get("/metrics").text
    assert 'http_requests_total{method="GET",endpoint="/api/v1/nonexistent",status="404"}' in body or 'http_requests_total{method="GET",endpoint="/api/v1/nonexistent",status="405"}' in body


def test_websocket_gauge_helper_roundtrip():
    prometheus_metrics.reset()
    increment_websocket_connections()
    decrement_websocket_connections()
    body = prometheus_metrics.render()
    assert "websocket_connections_active 0.0" in body
