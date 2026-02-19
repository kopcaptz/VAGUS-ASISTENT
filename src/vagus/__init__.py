"""
Vagus Asistent - ???????????? ???????? ???????.
"""

# ???? 1: ???? LLM
from .layer1 import (
    LLMRouter,
    BaseProvider,
    ProviderFactory,
    BaseBalancingStrategy,
    HybridStrategy,
    CircuitBreaker,
    FallbackHandler,
    MonitoringService,
    CacheService,
    BudgetingService,
)

# ???? 0: ??????? ?????? (ConfigManager ????? ??????????? ??? ????????)
def __getattr__(name):
    if name in ("ConfigManager", "AppConfig"):
        from .layer0.config import ConfigManager, AppConfig
        return ConfigManager if name == "ConfigManager" else AppConfig
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
