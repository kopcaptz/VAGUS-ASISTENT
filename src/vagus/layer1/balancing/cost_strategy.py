"""
Стратегия выбора провайдера по минимальной стоимости.
"""

import sys
from typing import Dict, Any
from .base_strategy import BaseBalancingStrategy


class CostStrategy(BaseBalancingStrategy):
    """Выбор провайдера с минимальной стоимостью."""

    def select_provider(
        self,
        providers: Dict[str, Any],
        request_context: Dict[str, Any],
    ) -> str:
        """
        Выбирает провайдера с минимальной оценкой стоимости.

        providers[pid] должен содержать ключ "cost" (float) или "estimated_cost".
        """
        if not providers:
            raise ValueError("No providers available")

        best_id = None
        best_cost = sys.float_info.max

        for pid, info in providers.items():
            cost = info.get("cost") or info.get("estimated_cost")
            if cost is None:
                cost = 0.0
            if cost < best_cost:
                best_cost = cost
                best_id = pid

        if best_id is None:
            raise ValueError("No providers with cost info available")
        return best_id
