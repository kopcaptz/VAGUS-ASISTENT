"""
Стратегия выбора провайдера по максимальному качеству.
"""

from typing import Dict, Any
from .base_strategy import BaseBalancingStrategy


class QualityStrategy(BaseBalancingStrategy):
    """Выбор провайдера с максимальной оценкой качества."""

    def select_provider(
        self,
        providers: Dict[str, Any],
        request_context: Dict[str, Any],
    ) -> str:
        """
        Выбирает провайдера с максимальной оценкой качества.

        providers[pid] должен содержать "quality" (float 0..1).
        """
        if not providers:
            raise ValueError("No providers available")

        best_id = None
        best_quality = -1.0

        for pid, info in providers.items():
            q = info.get("quality")
            if q is None:
                q = 0.5
            if q > best_quality:
                best_quality = q
                best_id = pid

        if best_id is None:
            raise ValueError("No providers with quality info available")
        return best_id
