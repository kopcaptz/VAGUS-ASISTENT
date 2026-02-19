"""
Tests for ConfigManager.get() and ConfigManager.set() methods.
Uses a temporary YAML file to avoid touching real configs.
"""

import os
import tempfile

import pytest
import yaml

from vagus.layer0.config.config_manager import ConfigManager


@pytest.fixture
def tmp_config():
    """Creates a temporary YAML config file and returns its path."""
    data = {
        "version": 1,
        "name": "Test",
        "global": {
            "default_model": "gpt-4o-mini",
            "log_level": "INFO",
            "workspace_path": "/tmp/ws",
            "max_concurrent_requests": 5,
            "api_timeout": 20,
        },
        "layer1": {
            "router": {"enable_cache": True, "default_strategy": "hybrid"},
            "cache": {"ttl_seconds": 3600, "max_size_mb": 50},
            "budgeting": {"daily_limit_usd": 5.0, "monthly_limit_usd": 50.0},
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(data, f)
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
def cm(tmp_config):
    return ConfigManager(config_path=tmp_config, enable_hot_reload=False)


class TestGet:

    def test_get_global(self, cm):
        cm.load()
        assert cm.get("global.default_model") == "gpt-4o-mini"

    def test_get_layer1_cache(self, cm):
        cm.load()
        assert cm.get("layer1.cache.ttl_seconds") == 3600

    def test_get_layer1_router(self, cm):
        cm.load()
        assert cm.get("layer1.router.enable_cache") is True

    def test_get_missing_returns_default(self, cm):
        cm.load()
        assert cm.get("nonexistent.path", default=42) == 42

    def test_get_nested_missing_returns_default(self, cm):
        cm.load()
        assert cm.get("layer1.nonexistent.field", default="nope") == "nope"


class TestSet:

    def test_set_layer1_cache_ttl(self, cm):
        cm.load()
        cm.set("layer1.cache.ttl_seconds", 7200)
        assert cm.get("layer1.cache.ttl_seconds") == 7200

    def test_set_global_model(self, cm):
        cm.load()
        cm.set("global.default_model", "claude-3")
        assert cm.get("global.default_model") == "claude-3"

    def test_set_invalid_path_raises(self, cm):
        cm.load()
        with pytest.raises(KeyError):
            cm.set("totally.invalid.path", "value")
