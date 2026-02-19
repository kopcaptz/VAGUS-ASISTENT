"""Тесты роутера статуса /api/v1/status/."""

import pytest


def test_system_status(client, admin_headers):
    resp = client.get("/api/v1/status", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "layer1_stats" in data
    assert "layer2_agents_count" in data
    assert data["layer2_agents_count"] == 3
    assert "active_tasks_count" in data
    assert "uptime_seconds" in data
    assert data["uptime_seconds"] >= 0


def test_status_has_layer1_stats(client, admin_headers):
    resp = client.get("/api/v1/status", headers=admin_headers)
    data = resp.json()
    l1 = data["layer1_stats"]
    assert l1.get("requests") == 42
    assert l1.get("total_cost") == 0.05


def test_status_requires_auth(client):
    resp = client.get("/api/v1/status")
    assert resp.status_code == 401
