"""Tests for Stage 4 admin resilience endpoints."""

from types import SimpleNamespace


def test_dead_letter_queue_endpoint_returns_entries(app, client, admin_headers):
    app.state.dead_letter_queue.add_failed_task(
        task_id="dlq-1",
        agent_type="coder",
        error_message="timeout",
        stack_trace="trace",
        retry_count=0,
        task_payload={"prompt": "hello", "task_type": "code"},
    )
    response = client.get("/api/v1/admin/dead-letter-queue?limit=10", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert payload[0]["task_id"] == "dlq-1"
    assert payload[0]["agent_type"] == "coder"


def test_dead_letter_queue_requires_admin(client, user_headers):
    response = client.get("/api/v1/admin/dead-letter-queue", headers=user_headers)
    assert response.status_code == 403


def test_dead_letter_queue_manual_fix_endpoint(app, client, admin_headers):
    app.state.dead_letter_queue.add_failed_task(
        task_id="dlq-2",
        agent_type="researcher",
        error_message="network_error",
        stack_trace="trace",
        retry_count=1,
    )
    response = client.post(
        "/api/v1/admin/dead-letter-queue/dlq-2/manual-fix",
        json={"note": "manually resolved"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "manually_fixed"
    assert payload["manual_fix_note"] == "manually resolved"


def test_dead_letter_queue_retry_endpoint(app, client, admin_headers):
    app.state.dead_letter_queue.add_failed_task(
        task_id="dlq-3",
        agent_type="analyst",
        error_message="timeout",
        stack_trace="trace",
        retry_count=0,
        task_payload={"prompt": "retry me", "task_type": "analysis", "metadata": {"source": "dlq"}},
    )
    response = client.post(
        "/api/v1/admin/dead-letter-queue/dlq-3/retry",
        json={},
        headers=admin_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == "dlq-3"
    assert payload["success"] is True
    assert payload["retry_count"] == 1
    assert "retry_task_id" in payload


def test_circuit_breaker_dashboard_and_reset_endpoint(app, client, admin_headers):
    class _Breaker:
        def __init__(self, state_name: str):
            self._state = state_name
            self.reset_called = False

        @property
        def state(self):
            return SimpleNamespace(name=self._state)

        def get_stats(self):
            return {
                "failure_count": 3,
                "success_rate": 62.5,
                "recovery_timeout": 60,
                "failure_threshold": 3,
                "total_success_count": 5,
                "total_failure_count": 3,
                "last_failure_iso": "2026-02-19T00:00:00+00:00",
            }

        def reset(self):
            self._state = "CLOSED"
            self.reset_called = True

    breaker = _Breaker("OPEN")
    app.state.llm_router.fallback_handler = SimpleNamespace(_circuit_breakers={"openai": breaker})

    get_resp = client.get("/api/v1/admin/circuit-breakers", headers=admin_headers)
    assert get_resp.status_code == 200
    payload = get_resp.json()
    assert "breakers" in payload
    assert payload["breakers"][0]["provider_id"] == "openai"
    assert payload["breakers"][0]["state"] == "open"
    assert "history" in payload

    reset_resp = client.post("/api/v1/admin/circuit-breakers/openai/reset", headers=admin_headers)
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "reset"
    assert breaker.reset_called is True


def test_error_analytics_endpoint_returns_snapshot(app, client, admin_headers):
    app.state.error_analytics.record_error(
        source="layer3.api.tasks",
        message="timeout exceeded",
        error_type="TimeoutError",
        metadata={"task_id": "x"},
    )
    app.state.error_analytics.record_error(
        source="layer1.router",
        message="validation failed",
        error_type="ValueError",
    )
    response = client.get(
        "/api/v1/admin/error-analytics?window_minutes=60&top_sources_limit=5",
        headers=admin_headers,
    )
    assert response.status_code == 200
    payload = response.json()
    assert "error_rate_by_type" in payload
    assert "top_error_sources" in payload
    assert "correlation" in payload
    assert "recent_events" in payload
