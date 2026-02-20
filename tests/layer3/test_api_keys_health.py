"""Tests for API keys health endpoints."""

from __future__ import annotations

from vagus.security import KeyManager


def _reset_singleton() -> None:
    KeyManager.reset_instance_for_tests()


def test_api_keys_health_endpoint(client, admin_headers, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _reset_singleton()

    create_resp = client.post(
        "/api/v1/keys",
        json={
            "name": "openai",
            "type": "openai",
            "value": "sk-test-1234567890",
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 201

    health_resp = client.get("/api/v1/keys/health", headers=admin_headers)
    assert health_resp.status_code == 200
    payload = health_resp.json()
    assert payload["total_keys"] >= 1
    assert "keys" in payload
    assert isinstance(payload["keys"], list)


def test_api_keys_health_check_endpoint(client, admin_headers, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _reset_singleton()

    client.post(
        "/api/v1/keys",
        json={
            "name": "openai",
            "type": "openai",
            "value": "sk-test-1234567890",
        },
        headers=admin_headers,
    )

    # Avoid network dependency in tests.
    monkeypatch.setattr(KeyManager, "_validate_online", lambda self, **_: (True, None))
    check_resp = client.post("/api/v1/keys/health/check", headers=admin_headers)
    assert check_resp.status_code == 200
    payload = check_resp.json()
    assert payload["total_keys"] >= 1
