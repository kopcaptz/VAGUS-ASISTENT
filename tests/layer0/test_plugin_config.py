"""Tests for plugin configuration schema."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from vagus.layer0.config.models import AppConfig


def test_app_config_plugins_defaults():
    config = AppConfig.model_validate({"global": {}})

    assert config.plugins.enabled is True
    assert config.plugins.auto_discover is True
    assert "./plugins" in config.plugins.scan_directories
    assert config.plugins.sandbox.memory_limit_mb == 512
    assert config.plugins.marketplace.url == "https://plugins.vagus.ai"


def test_app_config_plugins_rejects_empty_scan_directories():
    with pytest.raises(ValidationError):
        AppConfig.model_validate(
            {
                "global": {},
                "plugins": {"scan_directories": []},
            }
        )


def test_example_yaml_has_plugin_section():
    config_path = Path(__file__).resolve().parents[2] / "configs" / "vagus.yaml.example"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert isinstance(payload, dict)
    assert "plugins" in payload
    assert payload["plugins"]["sandbox"]["timeout_seconds"] == 30
