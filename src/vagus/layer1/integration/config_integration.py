"""
Интеграция с конфигурацией (Слой 0).
Чтение layer1.* из конфигурации.
"""

from typing import Dict, Any, Optional


def get_layer1_config(config: Any) -> Dict[str, Any]:
    """
    Извлекает конфигурацию layer1 из AppConfig или dict.

    Args:
        config: AppConfig или словарь конфигурации

    Returns:
        Словарь настроек layer1
    """
    if config is None:
        return {}
    if hasattr(config, "model_dump"):
        data = config.model_dump()
    elif isinstance(config, dict):
        data = config
    else:
        return {}
    return data.get("layer1", {})


def build_router_kwargs(config: Any) -> Dict[str, Any]:
    """
    Строит kwargs для LLMRouter из конфигурации.

    Args:
        config: AppConfig или dict

    Returns:
        Словарь аргументов для LLMRouter
    """
    layer1 = get_layer1_config(config)
    router_cfg = layer1.get("router", {})
    cache_cfg = layer1.get("cache", {})
    if not isinstance(cache_cfg, dict):
        cache_cfg = {}
    secondary_cache_cfg = cache_cfg.get("secondary", {})
    if not isinstance(secondary_cache_cfg, dict):
        secondary_cache_cfg = {}
    budget_cfg = layer1.get("budgeting", {})
    mon_cfg = layer1.get("monitoring", {})
    fallback_cfg = layer1.get("fallback", {})
    cb_cfg = fallback_cfg.get("circuit_breaker", {})
    http_cfg = layer1.get("http", {})
    if not isinstance(http_cfg, dict):
        http_cfg = {}
    retry_cfg = layer1.get("retry", {})
    if not isinstance(retry_cfg, dict):
        retry_cfg = {}
    # Allow top-level retry section too for runtime YAML compatibility.
    top_level_retry = {}
    if hasattr(config, "model_dump"):
        data = config.model_dump()
        top_level_retry = data.get("retry", {}) if isinstance(data, dict) else {}
    elif isinstance(config, dict):
        top_level_retry = config.get("retry", {})
    if isinstance(top_level_retry, dict) and top_level_retry:
        retry_cfg = {**retry_cfg, **top_level_retry}

    return {
        "enable_cache": router_cfg.get("enable_cache", True),
        "enable_budgeting": router_cfg.get("enable_budgeting", True),
        "enable_monitoring": router_cfg.get("enable_monitoring", True),
        "default_strategy": router_cfg.get("default_strategy", "hybrid"),
        "cache_ttl": cache_cfg.get("ttl_seconds", 3600),
        "cache_max_mb": cache_cfg.get("max_size_mb", 100),
        "cache_secondary_enabled": secondary_cache_cfg.get("enabled", False),
        "cache_secondary_redis_url": secondary_cache_cfg.get("redis_url"),
        "cache_secondary_sqlite_path": secondary_cache_cfg.get(
            "sqlite_fallback_path",
            "cache_fallback.db",
        ),
        "cache_secondary_namespace_ttls": {
            "llm_response": secondary_cache_cfg.get("llm_responses_ttl_seconds", 3600),
            "provider_health": secondary_cache_cfg.get("provider_health_ttl_seconds", 120),
            "rate_limit_counter": secondary_cache_cfg.get("rate_limit_counter_ttl_seconds", 60),
            "session_data": secondary_cache_cfg.get("session_data_ttl_seconds", 3600),
        },
        "budget_daily": budget_cfg.get("daily_limit_usd", 10.0),
        "budget_monthly": budget_cfg.get("monthly_limit_usd", 200.0),
        "monitoring_db": mon_cfg.get("db_path", "metrics.db"),
        "monitoring_retention_days": mon_cfg.get("retention_days", 30),
        "fallback_max_retries": fallback_cfg.get("max_retries", 3),
        "fallback_base_delay": fallback_cfg.get("base_delay_seconds", 1.0),
        "fallback_chain": fallback_cfg.get("providers"),
        "retry_max_attempts": retry_cfg.get("max_attempts", 5),
        "retry_backoff_factor": retry_cfg.get("backoff_factor", 2.0),
        "retry_retryable_errors": retry_cfg.get(
            "retryable_errors",
            ["timeout", "rate_limit", "network_error"],
        ),
        "http_max_connections": http_cfg.get("max_connections", 100),
        "http_max_keepalive_connections": http_cfg.get("max_keepalive_connections", 20),
        "http_keepalive_expiry": http_cfg.get("keepalive_expiry", 5.0),
    }
