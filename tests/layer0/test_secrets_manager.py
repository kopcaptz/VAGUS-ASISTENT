"""Тесты SecretsManager (local/vault fallback)."""

from __future__ import annotations

import json

from vagus.layer0.config.secrets_manager import SecretsManager


def test_local_secrets_manager_reads_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-secret")
    manager = SecretsManager(backend="local")
    assert manager.get_secret("OPENAI_API_KEY") == "env-secret"


def test_local_secrets_manager_reads_local_file(tmp_path, monkeypatch):
    secrets_file = tmp_path / "secrets.json"
    secrets_file.write_text(json.dumps({"OPENAI_API_KEY": "file-secret"}), encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("VAGUS_LOCAL_SECRETS_FILE", str(secrets_file))

    manager = SecretsManager(backend="local")
    assert manager.get_secret("OPENAI_API_KEY") == "file-secret"


def test_vault_backend_falls_back_to_local_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fallback-local-secret")
    manager = SecretsManager(
        backend="vault",
        vault_addr="http://127.0.0.1:8200",
        vault_token="",  # no token -> vault unavailable -> fallback
    )
    assert manager.get_secret("OPENAI_API_KEY") == "fallback-local-secret"


def test_get_provider_api_key_uses_provider_name(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    manager = SecretsManager(backend="local")
    assert manager.get_provider_api_key("anthropic") == "anthropic-secret"
