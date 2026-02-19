"""
Трекер задержек (TTFT и E2E) для запросов LLM.
"""

import time
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from ...layer0.logging import get_logger


class LatencyTracker:
    """Трекер Time-to-First-Token (TTFT) и End-to-End (E2E) задержек."""

    def __init__(self):
        self.logger = get_logger("monitoring.latency_tracker")

    @asynccontextmanager
    async def track(self, trace_id: str):
        """
        Контекстный менеджер для измерения E2E latency.

        Args:
            trace_id: Уникальный ID запроса

        Yields:
            dict с полями start_time, ttft_ms (устанавливается вручную),
            e2e_ms (вычисляется при выходе)
        """
        ctx: Dict[str, Any] = {
            "trace_id": trace_id,
            "start_time": time.monotonic(),
            "ttft_ms": None,
            "e2e_ms": None,
        }
        try:
            yield ctx
        finally:
            ctx["e2e_ms"] = (time.monotonic() - ctx["start_time"]) * 1000
            ttft_val = ctx.get("ttft_ms")
            e2e_val = ctx.get("e2e_ms")
            if e2e_val is not None:
                self.logger.debug(
                    f"Latency tracked: trace_id={trace_id[:8]}..., "
                    f"ttft={ttft_val}ms, e2e={e2e_val:.1f}ms"
                )

    def record_ttft(self, ctx: Dict[str, Any], ttft_ms: float) -> None:
        """
        Записывает TTFT в контекст (вызывается при получении первого токена).

        Args:
            ctx: Контекст из track()
            ttft_ms: Time to first token в миллисекундах
        """
        if ctx.get("ttft_ms") is None:
            ctx["ttft_ms"] = ttft_ms
