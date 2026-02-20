from __future__ import annotations

import os
from pathlib import Path

from vagus.security import KeyManager


def _reset_singleton() -> None:
    KeyManager.reset_instance_for_tests()


def test_key_manager_crypto_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("VAGUS_KEYS_MASTER_KEY", raising=False)
    _reset_singleton()
    manager = KeyManager()

    created = manager.add_key(name="openai", key_type="openai", value="sk-test-1234567890")
    assert created["name"] == "openai"
    assert manager.get_key("openai") == "sk-test-1234567890"

    keys_file = tmp_path / ".vagus" / "keys.enc"
    raw = keys_file.read_text(encoding="utf-8")
    assert "sk-test-1234567890" not in raw


def test_key_manager_env_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("VAGUS_KEYS_MASTER_KEY", raising=False)
    _reset_singleton()
    manager = KeyManager()
    manager.add_key(name="openai", key_type="openai", value="sk-store-1234567890")

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-override")
    assert manager.get_key("openai") == "sk-env-override"

    listed = manager.list_keys()["openai"]
    assert listed["source"] == "env"
