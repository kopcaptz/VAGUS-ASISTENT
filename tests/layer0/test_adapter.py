"""
Tests for the config adapter module.
Verifies env fallback behaviour and integration with ConfigManager.
"""

import os
import tempfile

import pytest
import yaml

from vagus.layer0.adapters import (
    bind,
    config_adapter,
    get,
    get_bool,
    get_float,
    get_int,
    get_manager,
)
from vagus.layer0.config.config_manager import ConfigManager

import vagus.layer0.adapters as _adapter_mod


@pytest.fixture(autouse=True)
def reset_adapter():
    """Unbinds the adapter before and after each test."""
    _adapter_mod._instance = None
    yield
    _adapter_mod._instance = None


class TestAdapterWithoutBinding:
    """When no ConfigManager is bound, adapter falls back to env / defaults."""

    def test_get_returns_default(self):
        assert get("some.path", default="fallback") == "fallback"

    def test_get_from_env(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "from_env")
        assert get("some.path", env_fallback="MY_VAR", default="nope") == "from_env"

    def test_get_int_default(self):
        assert get_int("x.y.z", default=42) == 42

    def test_get_float_default(self):
        assert get_float("x", default=3.14) == 3.14

    def test_get_bool_default(self):
        assert get_bool("x", default=True) is True

    def test_get_bool_from_env(self, monkeypatch):
        monkeypatch.setenv("BOOL_VAR", "true")
        assert get_bool("x", env_fallback="BOOL_VAR") is True

    def test_get_manager_returns_none(self):
        assert get_manager() is None


class TestAdapterWithBinding:

    @pytest.fixture
    def bound_cm(self):
        data = {
            "version": 1,
            "global": {"default_model": "gpt-4"},
            "layer1": {"cache": {"ttl_seconds": 9999}},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            path = f.name
        cm = ConfigManager(config_path=path, enable_hot_reload=False)
        cm.load()
        bind(cm)
        yield cm
        os.unlink(path)

    def test_get_from_config(self, bound_cm):
        assert get("layer1.cache.ttl_seconds") == 9999

    def test_env_overrides_config(self, bound_cm, monkeypatch):
        monkeypatch.setenv("OVERRIDE_TTL", "1234")
        assert get("layer1.cache.ttl_seconds", env_fallback="OVERRIDE_TTL") == "1234"

    def test_get_int_from_config(self, bound_cm):
        assert get_int("layer1.cache.ttl_seconds") == 9999

    def test_config_adapter_proxy(self, bound_cm):
        assert config_adapter.get("layer1.cache.ttl_seconds") == 9999
        assert config_adapter.get_manager() is bound_cm
