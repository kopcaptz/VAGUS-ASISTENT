"""
Unit tests for the Status REST API.
"""

import pytest


class TestSystemStatus:

    def test_get_status(self, client, auth_headers):
        response = client.get("/api/v1/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "layer1_stats" in data
        assert "layer2_agents_count" in data
        assert "active_tasks_count" in data
        assert "uptime_seconds" in data

    def test_get_status_unauthorized(self, client):
        response = client.get("/api/v1/status")
        assert response.status_code == 401
