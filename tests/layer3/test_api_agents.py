"""Тесты роутера агентов /api/v1/agents/."""

import pytest


def test_list_agents(client, admin_headers):
    resp = client.get("/api/v1/agents", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    names = {a["name"] for a in data}
    assert "researcher" in names
    assert "coder" in names
    assert "analyst" in names


def test_agents_have_task_types(client, admin_headers):
    resp = client.get("/api/v1/agents", headers=admin_headers)
    for agent in resp.json():
        assert len(agent["task_types"]) > 0
        assert agent["is_available"] is True


def test_agents_require_auth(client):
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 401
