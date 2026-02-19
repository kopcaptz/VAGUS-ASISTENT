"""Тесты health endpoint и общей работы приложения."""

import pytest


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_docs(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["info"]["title"] == "Vagus Asistent API"
    assert data["info"]["version"] == "1.0.0"


def test_invalid_endpoint(client):
    resp = client.get("/api/v1/nonexistent")
    assert resp.status_code in (404, 405)
