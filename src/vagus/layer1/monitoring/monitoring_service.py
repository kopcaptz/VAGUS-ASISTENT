"""
Основной сервис мониторинга для Слоя 1.
"""

from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
from .metrics_storage import MetricsStorage
from .latency_tracker import LatencyTracker
from .cost_tracker import CostTracker
from .quality_monitor import QualityMonitor
from .metrics_collector import MetricsCollector
from ...layer0.logging import get_logger


class MonitoringService:
    """Фасад мониторинга: хранилище, трекеры, сбор метрик."""

    def __init__(
        self,
        db_path: str = "metrics.db",
        retention_days: int = 30,
    ):
        """
        Инициализация сервиса мониторинга.

        Args:
            db_path: Путь к SQLite базе метрик
            retention_days: Хранение метрик за N дней
        """
        self.db_path = db_path
        self.retention_days = retention_days
        self.storage = MetricsStorage(db_path)
        self.latency_tracker = LatencyTracker()
        self.cost_tracker = CostTracker()
        self.quality_monitor = QualityMonitor()
        self.metrics_collector = MetricsCollector(
            storage=self.storage,
            latency_tracker=self.latency_tracker,
            cost_tracker=self.cost_tracker,
            quality_monitor=self.quality_monitor,
        )
        self.logger = get_logger("monitoring")
        self.logger.info(
            f"MonitoringService инициализирован (db={db_path}, retention={retention_days}d)"
        )

    @asynccontextmanager
    async def track_request(self, trace_id: Optional[str] = None):
        """
        Контекстный менеджер для отслеживания запроса.

        Yields:
            dict с полями trace_id, latency_ctx, record_complete()
        """
        trace_id = trace_id or MetricsStorage.generate_trace_id()
        async with self.latency_tracker.track(trace_id) as latency_ctx:
            ctx = {
                "trace_id": trace_id,
                "latency_ctx": latency_ctx,
                "record_complete": lambda **kwargs: self._record_complete(
                    trace_id, latency_ctx, **kwargs
                ),
            }
            yield ctx

    def _record_complete(
        self,
        trace_id: str,
        latency_ctx: Dict[str, Any],
        provider: str,
        model: str,
        success: bool,
        cost_usd: float = 0.0,
        error_type: Optional[str] = None,
    ) -> None:
        """Внутренний метод записи завершённого запроса."""
        self.metrics_collector.record_request(
            trace_id=trace_id,
            provider=provider,
            model=model,
            success=success,
            ttft_ms=latency_ctx.get("ttft_ms"),
            e2e_ms=latency_ctx.get("e2e_ms"),
            cost_usd=cost_usd,
            error_type=error_type,
        )

    def record_complete_request(
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
        Записывает завершённый запрос (без контекста).

        Args:
            trace_id: ID запроса
            provider: Провайдер
            model: Модель
            success: Успешность
            ttft_ms: Time to first token
            e2e_ms: End-to-end latency
            cost_usd: Стоимость
            error_type: Тип ошибки
        """
        self.metrics_collector.record_request(
            trace_id=trace_id,
            provider=provider,
            model=model,
            success=success,
            ttft_ms=ttft_ms,
            e2e_ms=e2e_ms,
            cost_usd=cost_usd,
            error_type=error_type,
        )

    def get_stats(
        self,
        provider: Optional[str] = None,
        retention_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Возвращает агрегированную статистику."""
        return self.storage.get_stats(
            provider=provider,
            retention_days=retention_days or self.retention_days,
        )

    def cleanup_old(self, retention_days: Optional[int] = None) -> int:
        """Удаляет устаревшие метрики."""
        return self.storage.cleanup_old(
            retention_days or self.retention_days
        )
