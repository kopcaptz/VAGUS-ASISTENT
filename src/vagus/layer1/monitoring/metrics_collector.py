"""
Сборщик метрик для запросов LLM.
"""

from typing import Dict, Any, Optional
from .metrics_storage import MetricsStorage
from .latency_tracker import LatencyTracker
from .cost_tracker import CostTracker
from .quality_monitor import QualityMonitor
from ...layer0.logging import get_logger


class MetricsCollector:
    """Агрегирует метрики и записывает в хранилище."""

    def __init__(
        self,
        storage: MetricsStorage,
        latency_tracker: LatencyTracker,
        cost_tracker: CostTracker,
        quality_monitor: QualityMonitor,
    ):
        self.storage = storage
        self.latency_tracker = latency_tracker
        self.cost_tracker = cost_tracker
        self.quality_monitor = quality_monitor
        self.logger = get_logger("monitoring.metrics_collector")

    def record_request(
        self,
        trace_id: str,
        provider: str,
        model: str,
        success: bool,
        ttft_ms: Optional[float] = None,
        e2e_ms: Optional[float] = None,
        cost_usd: float = 0.0,
        error_type: Optional[str] = None,
    ) -> None:
        """
        Записывает метрики завершённого запроса.

        Args:
            trace_id: ID запроса
            provider: Провайдер
            model: Модель
            success: Успешность
            ttft_ms: Time to first token
            e2e_ms: End-to-end latency
            cost_usd: Стоимость
            error_type: Тип ошибки при неуспехе
        """
        self.storage.insert(
            trace_id=trace_id,
            provider=provider,
            model=model,
            ttft_ms=ttft_ms,
            e2e_ms=e2e_ms,
            cost_usd=cost_usd,
            success=success,
            error_type=error_type,
        )
        self.logger.debug(f"Metrics recorded: {trace_id[:8]}..., provider={provider}")
