"""
Стратегия выбора провайдера по минимальной задержке.
"""

import sys
from typing import Dict, Any
from .base_strategy import BaseBalancingStrategy


class LatencyStrategy(BaseBalancingStrategy):
    """Выбор провайдера с минимальной задержкой (E2E или TTFT)."""

    def __init__(self, use_ttft: bool = False):
        """
        Args:
            use_ttft: Если True, использовать ttft_ms; иначе e2e_ms
        """
        self.use_ttft = use_ttft

    def select_provider(
        self,
        providers: Dict[str, Any],
        request_context: Dict[str, Any],
    ) -> str:
        """
        Выбирает провайдера с минимальной задержкой.

        providers[pid] должен содержать "latency", "e2e_ms" или "ttft_ms".
        """
        if not providers:
            raise ValueError("No providers available")

        key = "ttft_ms" if self.use_ttft else "e2e_ms"
        alt_key = "latency"

        best_id = None
        best_latency = sys.float_info.max

        for pid, info in providers.items():
            lat = info.get(key) or info.get(alt_key)
            if lat is None:
                lat = sys.float_info.max
            if lat < best_latency:
                best_latency = lat
                best_id = pid

        if best_id is None:
            raise ValueError("No providers with latency info available")
        return best_id
