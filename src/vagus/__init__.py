"""
Vagus Asistent - ???????????? ???????? ???????.
"""

_LAYER0_EXPORTS = {"ConfigManager", "AppConfig"}
_LAYER1_EXPORTS = {
    "LLMRouter",
    "BaseProvider",
    "ProviderFactory",
    "BaseBalancingStrategy",
    "HybridStrategy",
    "CircuitBreaker",
    "FallbackHandler",
    "MonitoringService",
    "CacheService",
    "BudgetingService",
}


def __getattr__(name):
    if name in _LAYER0_EXPORTS:
        from .layer0.config import AppConfig, ConfigManager

        return ConfigManager if name == "ConfigManager" else AppConfig
    if name in _LAYER1_EXPORTS:
        from . import layer1

        return getattr(layer1, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ConfigManager",
    "AppConfig",
    "LLMRouter",
    "BaseProvider",
    "ProviderFactory",
    "BaseBalancingStrategy",
    "HybridStrategy",
    "CircuitBreaker",
    "FallbackHandler",
    "MonitoringService",
    "CacheService",
    "BudgetingService",
]
