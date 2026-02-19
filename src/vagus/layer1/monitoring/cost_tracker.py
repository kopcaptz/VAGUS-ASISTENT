"""
Трекер стоимости запросов.
Делегирует расчёт провайдерам и интегрируется с BudgetingService.
"""

from typing import Optional
from ...layer0.logging import get_logger


class CostTracker:
    """Трекер стоимости запросов к LLM."""

    def __init__(self):
        self.logger = get_logger("monitoring.cost_tracker")

    def calculate_cost(
        self,
        provider,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """
        Рассчитывает стоимость запроса через calculate_cost провайдера.

        Args:
            provider: Провайдер LLM с методом calculate_cost
            prompt_tokens: Токены промпта
            completion_tokens: Токены ответа

        Returns:
            Стоимость в USD
        """
        try:
            cost = provider.calculate_cost(prompt_tokens, completion_tokens)
            return round(cost, 6)
        except Exception as e:
            self.logger.warning(f"Cost calculation failed: {e}")
            return 0.0
