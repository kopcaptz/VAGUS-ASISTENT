"""
Менеджер стратегий балансировки.
"""

from typing import Dict, Any, Optional
from .base_strategy import BaseBalancingStrategy
from .cost_strategy import CostStrategy
from .latency_strategy import LatencyStrategy
from .quality_strategy import QualityStrategy
from .hybrid_strategy import HybridStrategy
from ...layer0.logging import get_logger


class StrategyManager:
    """Хранение и выбор стратегий балансировки."""

    def __init__(self):
        self._strategies: Dict[str, BaseBalancingStrategy] = {}
        self._default_name = "hybrid"
        self.logger = get_logger("balancing.strategy_manager")
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Регистрирует стандартные стратегии."""
        self.register("cost", CostStrategy())
        self.register("latency", LatencyStrategy())
        self.register("quality", QualityStrategy())
        self.register("hybrid", HybridStrategy())

    def register(self, name: str, strategy: BaseBalancingStrategy) -> None:
        """Регистрирует стратегию."""
        self._strategies[name] = strategy
        self.logger.debug(f"Strategy registered: {name}")

    def get_strategy(self, name: Optional[str] = None) -> BaseBalancingStrategy:
        """
        Возвращает стратегию по имени.

        Args:
            name: Имя стратегии или None для default

        Returns:
            Стратегия

        Raises:
            KeyError: Если стратегия не найдена
        """
        key = name or self._default_name
        if key not in self._strategies:
            raise KeyError(f"Strategy '{key}' not found. Available: {list(self._strategies.keys())}")
        return self._strategies[key]

    def set_default(self, name: str) -> None:
        """Устанавливает стратегию по умолчанию."""
        if name not in self._strategies:
            raise KeyError(f"Strategy '{name}' not found")
        self._default_name = name
        self.logger.info(f"Default strategy set to: {name}")

    def list_strategies(self) -> list:
        """Возвращает список зарегистрированных стратегий."""
        return list(self._strategies.keys())
