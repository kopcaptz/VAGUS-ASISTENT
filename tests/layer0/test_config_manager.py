"""Unit-тесты ConfigManager (Layer 0)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from vagus.layer0.config import ConfigManager


def _write_config(path: Path, *, api_timeout: int = 30, with_version: bool = True) -> None:
    data = {
        "version": 1,
        "name": "Vagus Test",
        "global": {
            "default_model": "gpt-4o-mini",
            "log_level": "INFO",
            "workspace_path": "./workspace",
            "max_concurrent_requests": 5,
            "api_timeout": api_timeout,
        },
        "providers": {
            "openai": {
                "endpoint": "https://api.openai.com/v1",
                "rate_limit": 60,
                "timeout": 30,
                "enabled": True,
                "models": ["gpt-4o-mini"],
            }
        },
        "agents": {},
        "skills": {},
    }
    if not with_version:
        data.pop("version")
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_load_injects_env_and_calls_callback(tmp_path, monkeypatch):
    cfg_path = tmp_path / "vagus.yaml"
    _write_config(cfg_path, api_timeout=30)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")

    calls: list[int] = []
    manager = ConfigManager(
        config_path=str(cfg_path),
        env_path=str(tmp_path / ".env"),
        enable_hot_reload=False,
    )
    manager.register_callback(lambda cfg: calls.append(cfg.global_settings.api_timeout))
    cfg = manager.load()

    assert cfg.name == "Vagus Test"
    assert cfg.providers["openai"].api_key.get_secret_value() == "sk-test-openai"
    assert calls == [30]


def test_load_uses_cache_and_force_reload(tmp_path, monkeypatch):
    cfg_path = tmp_path / "vagus.yaml"
    _write_config(cfg_path, api_timeout=30)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")

    manager = ConfigManager(config_path=str(cfg_path), enable_hot_reload=False)
    cfg1 = manager.load()
    cfg2 = manager.load()
    assert cfg1 is cfg2
    assert cfg1.global_settings.api_timeout == 30

    time.sleep(0.01)
    _write_config(cfg_path, api_timeout=45)
    cfg3 = manager.load(force_reload=True)
    assert cfg3.global_settings.api_timeout == 45


def test_load_missing_file_raises_file_not_found(tmp_path):
    manager = ConfigManager(config_path=str(tmp_path / "missing.yaml"), enable_hot_reload=False)
    with pytest.raises(FileNotFoundError):
        manager.load()


def test_load_invalid_config_raises_value_error(tmp_path):
    cfg_path = tmp_path / "vagus.yaml"
    _write_config(cfg_path, with_version=False)

    manager = ConfigManager(config_path=str(cfg_path), enable_hot_reload=False)
    with pytest.raises(ValueError):
        manager.load()


def test_save_default_config_creates_file(tmp_path):
    cfg_path = tmp_path / "default.yaml"
    manager = ConfigManager(config_path=str(cfg_path), enable_hot_reload=False)
    manager.save_default_config()

    assert cfg_path.exists()
    parsed = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert parsed["version"] == 1
    assert "providers" in parsed
