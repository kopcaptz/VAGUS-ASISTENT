"""
Гибридная стратегия: взвешенная сумма cost, latency, quality.
"""

from typing import Dict, Any, Optional
from .base_strategy import BaseBalancingStrategy

# Веса по умолчанию из ТЗ
DEFAULT_WEIGHTS = {
    "urgent": {"cost": 0.1, "latency": 0.8, "quality": 0.1},
    "normal": {"cost": 0.33, "latency": 0.33, "quality": 0.34},
    "low": {"cost": 0.8, "latency": 0.1, "quality": 0.1},
}


class HybridStrategy(BaseBalancingStrategy):
    """
    Гибридная стратегия:
    1. Сбор метрик: cost, latency, quality
    2. Нормализация к [0, 1] (инверсия для cost/latency — меньше = лучше)
    3. Взвешивание по priority (urgent/normal/low)
    4. Выбор провайдера с максимальной оценкой
    """

    def __init__(self, weights: Optional[Dict[str, Dict[str, float]]] = None):
        """
        Args:
            weights: Кастомные веса {priority: {cost, latency, quality}}
                     По умолчанию используются DEFAULT_WEIGHTS
        """
        self.weights = weights or DEFAULT_WEIGHTS

    def _normalize(
        self,
        values: Dict[str, float],
        invert: bool = False,
    ) -> Dict[str, float]:
        """
        Нормализует значения к [0, 1].
        invert=True: меньшее значение -> большее (для cost, latency)
        """
        if not values:
            return {}
        min_v = min(values.values())
        max_v = max(values.values())
        span = max_v - min_v if max_v != min_v else 1.0
        result = {}
        for k, v in values.items():
            n = (v - min_v) / span
            if invert:
                n = 1.0 - n
            result[k] = max(0, min(1, n))
        return result

    def select_provider(
        self,
        providers: Dict[str, Any],
        request_context: Dict[str, Any],
    ) -> str:
        """
        Выбирает провайдера по взвешенной оценке.
        """
        if not providers:
            raise ValueError("No providers available")

        priority = request_context.get("priority", "normal")
        if priority not in self.weights:
            priority = "normal"
        w = self.weights[priority]

        costs = {}
        latencies = {}
        qualities = {}
        for pid, info in providers.items():
            costs[pid] = float(info.get("cost") or info.get("estimated_cost") or 0)
            latencies[pid] = float(info.get("latency") or info.get("e2e_ms") or 0)
            qualities[pid] = float(info.get("quality") or 0.5)

        norm_cost = self._normalize(costs, invert=True)
        norm_lat = self._normalize(latencies, invert=True)
        norm_qual = self._normalize(qualities, invert=False)

        best_id = None
        best_score = -1.0

        for pid in providers:
            score = (
                norm_cost.get(pid, 0) * w.get("cost", 0.33)
                + norm_lat.get(pid, 0) * w.get("latency", 0.33)
                + norm_qual.get(pid, 0) * w.get("quality", 0.34)
            )
            if score > best_score:
                best_score = score
                best_id = pid

        if best_id is None:
            raise ValueError("No providers available for hybrid selection")
        return best_id
