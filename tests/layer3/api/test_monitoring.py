"""Integration tests for monitoring API endpoints."""

import pytest


def test_monitoring_redis_requires_auth(client):
    resp = client.get("/api/v1/monitoring/redis")
    assert resp.status_code == 401


def test_monitoring_redis_with_token(client, admin_headers):
    resp = client.get("/api/v1/monitoring/redis", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "available" in data
    assert "consumer_groups" in data
    assert "dlq_count" in data


def test_monitoring_postgres_with_token(client, admin_headers):
    resp = client.get("/api/v1/monitoring/postgres", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "available" in data
    assert "artifacts_count" in data
    assert "relationships_count" in data


def test_monitoring_artifact_graph_with_token(client, admin_headers):
    resp = client.get("/api/v1/monitoring/artifact-graph?limit=10", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "edges" in data
    assert "available" in data


def test_monitoring_synaptic_with_token(client, admin_headers):
    resp = client.get("/api/v1/monitoring/synaptic", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "available" in data
    assert "buffer_size" in data
    assert "events_processed" in data
