"""Tests for API key management endpoints."""

from __future__ import annotations

from vagus.security import KeyManager


def _reset_singleton() -> None:
    KeyManager.reset_instance_for_tests()


def test_keys_endpoints_require_admin(client, user_headers, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    _reset_singleton()

    no_auth = client.get("/api/v1/keys")
    assert no_auth.status_code == 401

    user_resp = client.get("/api/v1/keys", headers=user_headers)
    assert user_resp.status_code == 403


def test_keys_crud_and_validate(client, admin_headers, tmp_path, monkeypatch):
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
    assert create_resp.json()["name"] == "openai"

    list_resp = client.get("/api/v1/keys", headers=admin_headers)
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert isinstance(payload.get("keys"), list)
    assert any(item["name"] == "openai" for item in payload["keys"])

    validate_resp = client.post("/api/v1/keys/openai/validate", headers=admin_headers)
    assert validate_resp.status_code == 200
    assert "valid" in validate_resp.json()

    update_resp = client.put(
        "/api/v1/keys/openai",
        json={"value": "sk-test-updated-1234567890"},
        headers=admin_headers,
    )
    assert update_resp.status_code == 200

    delete_resp = client.delete("/api/v1/keys/openai", headers=admin_headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted"] is True
