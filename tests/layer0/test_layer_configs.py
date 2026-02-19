"""
Tests for Layer 1/2/3 config Pydantic models.
Verifies that the new models work with defaults, don't break AppConfig,
and can be loaded from dicts matching the YAML structure.
"""

import pytest

from vagus.layer0.config.models import (
    AppConfig,
    GlobalConfig,
    Layer1CacheConfig,
    Layer1Config,
    Layer1FallbackConfig,
    Layer1RouterConfig,
    Layer2Config,
    Layer3Config,
)


class TestLayer1Config:

    def test_defaults(self):
        cfg = Layer1Config()
        assert cfg.router.enable_cache is True
        assert cfg.cache.ttl_seconds == 3600
        assert cfg.budgeting.daily_limit_usd == 10.0
        assert cfg.monitoring.retention_days == 30
        assert cfg.fallback.retry_count == 3
        assert cfg.fallback.backoff_factor == 2.0

    def test_from_dict(self):
        data = {
            "router": {"enable_cache": False, "default_strategy": "cost"},
            "cache": {"ttl_seconds": 7200, "max_size_mb": 200},
            "budgeting": {"daily_limit_usd": 5.0, "monthly_limit_usd": 50.0},
            "monitoring": {"db_path": "/tmp/m.db", "retention_days": 7},
            "fallback": {"retry_count": 5, "providers": ["openai"]},
        }
        cfg = Layer1Config(**data)
        assert cfg.router.enable_cache is False
        assert cfg.router.default_strategy == "cost"
        assert cfg.cache.ttl_seconds == 7200
        assert cfg.budgeting.daily_limit_usd == 5.0
        assert cfg.monitoring.db_path == "/tmp/m.db"
        assert cfg.fallback.retry_count == 5
        assert cfg.fallback.providers == ["openai"]

    def test_router_config_defaults(self):
        r = Layer1RouterConfig()
        assert r.enable_budgeting is True
        assert r.enable_monitoring is True
        assert r.default_strategy == "hybrid"


class TestLayer2Config:

    def test_defaults(self):
        cfg = Layer2Config()
        assert cfg.orchestrator.max_concurrency == 5
        assert cfg.orchestrator.task_timeout == 300
        assert cfg.memory.episodic_enabled is True
        assert cfg.memory.semantic_enabled is True


class TestLayer3Config:

    def test_defaults(self):
        cfg = Layer3Config()
        assert cfg.api.port == 8000
        assert cfg.auth.access_token_expire_minutes == 15

    def test_from_dict(self):
        data = {
            "api": {"port": 9000, "rate_limit_requests": 120},
            "auth": {"access_token_expire_minutes": 30},
        }
        cfg = Layer3Config(**data)
        assert cfg.api.port == 9000
        assert cfg.api.rate_limit_requests == 120
        assert cfg.auth.access_token_expire_minutes == 30


class TestAppConfigWithLayers:
    """AppConfig with optional layer1/layer2/layer3 fields."""

    def test_appconfig_without_layers_still_works(self):
        """Existing configs without layer sections must still load."""
        data = {
            "version": 1,
            "global": {"default_model": "gpt-4"},
        }
        cfg = AppConfig(**data)
        assert cfg.version == 1
        assert cfg.layer1.router.enable_cache is True  # defaults kick in
        assert cfg.layer2.orchestrator.max_concurrency == 5
        assert cfg.layer3.api.port == 8000

    def test_appconfig_with_layers(self):
        data = {
            "version": 1,
            "global": {"default_model": "gpt-4"},
            "layer1": {
                "router": {"enable_cache": False},
                "cache": {"ttl_seconds": 1800},
            },
            "layer2": {
                "orchestrator": {"max_concurrency": 10},
            },
            "layer3": {
                "api": {"port": 9000},
            },
        }
        cfg = AppConfig(**data)
        assert cfg.layer1.router.enable_cache is False
        assert cfg.layer1.cache.ttl_seconds == 1800
        assert cfg.layer2.orchestrator.max_concurrency == 10
        assert cfg.layer3.api.port == 9000

    def test_model_dump_includes_layers(self):
        data = {
            "version": 1,
            "global": {"default_model": "gpt-4"},
        }
        cfg = AppConfig(**data)
        dumped = cfg.model_dump()
        assert "layer1" in dumped
        assert "layer2" in dumped
        assert "layer3" in dumped
        assert dumped["layer1"]["router"]["enable_cache"] is True
