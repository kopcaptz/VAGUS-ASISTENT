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
    budget_cfg = layer1.get("budgeting", {})
    mon_cfg = layer1.get("monitoring", {})
    fallback_cfg = layer1.get("fallback", {})
    cb_cfg = fallback_cfg.get("circuit_breaker", {})
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
    }
