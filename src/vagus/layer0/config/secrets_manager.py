"""
Secrets manager with optional Hashicorp Vault backend.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional
from urllib import error, request


class _BaseSecretsBackend:
    def get_secret(self, key: str) -> Optional[str]:
        raise NotImplementedError


class _LocalSecretsBackend(_BaseSecretsBackend):
    """Reads secrets from environment and optional local JSON file."""

    def __init__(self, secrets_file: Optional[str] = None):
        self.secrets_file = Path(
            secrets_file or os.getenv("VAGUS_LOCAL_SECRETS_FILE", "~/.vagus/secrets.json")
        ).expanduser()

    def _read_file_secrets(self) -> dict:
        if not self.secrets_file.exists():
            return {}
        try:
            with open(self.secrets_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
        return {}

    def get_secret(self, key: str) -> Optional[str]:
        value = os.getenv(key)
        if value:
            return value
        return self._read_file_secrets().get(key)


class _VaultSecretsBackend(_BaseSecretsBackend):
    """Minimal HTTP client for Hashicorp Vault KV v2."""

    def __init__(self, vault_addr: Optional[str], vault_token: Optional[str]):
        self.vault_addr = (vault_addr or "").rstrip("/")
        self.vault_token = vault_token or ""

    def get_secret(self, key: str) -> Optional[str]:
        if not self.vault_addr or not self.vault_token:
            return None
        url = f"{self.vault_addr}/v1/secret/data/{key}"
        req = request.Request(
            url,
            method="GET",
            headers={
                "X-Vault-Token": self.vault_token,
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=5) as response:
                raw = response.read().decode("utf-8")
            payload = json.loads(raw)
            # KV v2: {"data": {"data": {...}}}
            data = payload.get("data", {}).get("data", {})
            if isinstance(data, dict):
                # Поддерживаем как {"value": "..."} так и прямой ключ
                if "value" in data and data["value"]:
                    return str(data["value"])
                if key in data and data[key]:
                    return str(data[key])
            return None
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError):
            return None


class SecretsManager:
    """Facade for local/vault secrets backends."""

    def __init__(
        self,
        *,
        backend: str = "local",
        vault_addr: Optional[str] = None,
        vault_token: Optional[str] = None,
    ):
        backend_normalized = (backend or "local").strip().lower()
        if backend_normalized == "vault":
            self._backend: _BaseSecretsBackend = _VaultSecretsBackend(vault_addr, vault_token)
            self._fallback = _LocalSecretsBackend()
        else:
            self._backend = _LocalSecretsBackend()
            self._fallback = None

    @classmethod
    def from_config(cls, config: Optional[dict]) -> "SecretsManager":
        cfg = config or {}
        return cls(
            backend=cfg.get("backend", "local"),
            vault_addr=cfg.get("vault_addr"),
            vault_token=cfg.get("vault_token"),
        )

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        value = self._backend.get_secret(key)
        if value:
            return value
        if self._fallback is not None:
            value = self._fallback.get_secret(key)
            if value:
                return value
        return default

    def get_provider_api_key(self, provider_name: str) -> Optional[str]:
        env_like_key = f"{provider_name.upper()}_API_KEY"
        return self.get_secret(env_like_key)
