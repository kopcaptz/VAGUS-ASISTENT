"""
Unit tests for the Agents REST API.
"""

from unittest.mock import MagicMock

import pytest


class TestListAgents:

    def test_list_agents_empty(self, client, auth_headers):
        client.app.state.orchestrator.agents = []
        response = client.get("/api/v1/agents", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_list_agents_with_agents(self, client, auth_headers):
        agent = MagicMock()
        agent.name = "researcher"
        agent.description = "Research agent"
        agent.TASK_TYPES = ("research", "search")
        client.app.state.orchestrator.agents = [agent]

        response = client.get("/api/v1/agents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "researcher"
        assert "research" in data[0]["task_types"]

    def test_list_agents_unauthorized(self, client):
        response = client.get("/api/v1/agents")
        assert response.status_code == 401
