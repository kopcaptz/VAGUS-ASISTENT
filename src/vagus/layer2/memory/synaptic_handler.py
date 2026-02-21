"""
SynapticTrainingHandler — обработка quality_gate.passed с буферизацией и strengthen_connections_batch.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Any, Callable, Optional

from ...layer0.logging import get_logger

FLUSH_HISTORY_LIMIT = 60


class SynapticTrainingHandler:
    """
    Обрабатывает quality_gate.passed: буферизация 50 событий или 100мс,
    вызов strengthen_connections_batch, DLQ при ошибках.
    """

    def __init__(
        self,
        artifact_kb: Any,
        *,
        buffer_size: int = 50,
        buffer_timeout_ms: int = 100,
        dlq_callback: Optional[Callable[[dict, Exception], Any]] = None,
    ) -> None:
        """
        Args:
            artifact_kb: ArtifactKnowledgeBase или ArtifactKnowledgeBasePG (strengthen_connections_batch).
            buffer_size: Flush при накоплении N событий.
            buffer_timeout_ms: Период flush по таймеру.
            dlq_callback: Вызывается при ошибке обработки (event_data, exc).
        """
        self._artifact_kb = artifact_kb
        self._buffer_size = buffer_size
        self._buffer_timeout_ms = buffer_timeout_ms
        self._dlq_callback = dlq_callback
        self._buffer: list[dict] = []
        self._lock = asyncio.Lock()
        self._flush_task: Optional[asyncio.Task[None]] = None
        self._shutdown = asyncio.Event()
        self._events_processed: int = 0
        self._flush_count: int = 0
        self._flush_history: list[tuple[float, int]] = []
        self.logger = get_logger("layer2.memory.synaptic_handler")

    async def start(self) -> None:
        """Запускает фоновый flush по таймеру."""
        if self._flush_task is not None:
            return
        self._shutdown.clear()
        self._flush_task = asyncio.create_task(self._flush_loop())
        self.logger.debug("SynapticTrainingHandler flush loop started")

    async def stop(self) -> None:
        """Останавливает фоновый flush и выполняет финальный flush."""
        self._shutdown.set()
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        await self._flush()
        self.logger.debug("SynapticTrainingHandler stopped")

    async def _flush_loop(self) -> None:
        """Цикл периодического flush каждые buffer_timeout_ms."""
        while not self._shutdown.is_set():
            try:
                await asyncio.wait_for(
                    self._shutdown.wait(),
                    timeout=self._buffer_timeout_ms / 1000.0,
                )
            except asyncio.TimeoutError:
                await self._flush()

    async def _flush(self) -> None:
        """Сбрасывает буфер в artifact_kb.strengthen_connections_batch."""
        async with self._lock:
            if not self._buffer:
                return
            updates_by_tenant: dict[str, list[dict]] = defaultdict(list)
            for item in self._buffer:
                tenant_id = item.get("tenant_id", "default")
                updates_by_tenant[tenant_id].append({
                    "source_id": item["source_id"],
                    "target_id": item["target_id"],
                    "score": item.get("score", 1.0),
                })
            self._buffer.clear()

        total_flushed = 0
        for tenant_id, updates in updates_by_tenant.items():
            if not updates:
                continue
            try:
                if hasattr(self._artifact_kb, "strengthen_connections_batch"):
                    await self._artifact_kb.strengthen_connections_batch(updates, tenant_id)
                    total_flushed += len(updates)
                    self.logger.debug("SynapticTrainingHandler flushed %d updates for tenant %s", len(updates), tenant_id)
            except Exception as exc:
                self.logger.warning("SynapticTrainingHandler flush failed for tenant %s: %s", tenant_id, exc)
                if self._dlq_callback:
                    try:
                        if asyncio.iscoroutinefunction(self._dlq_callback):
                            await self._dlq_callback({"tenant_id": tenant_id, "updates": updates}, exc)
                        else:
                            self._dlq_callback({"tenant_id": tenant_id, "updates": updates}, exc)
                    except Exception as cb_exc:
                        self.logger.warning("DLQ callback failed: %s", cb_exc)
        if total_flushed > 0:
            self._flush_count += 1
            self._flush_history.append((time.time(), total_flushed))
            if len(self._flush_history) > FLUSH_HISTORY_LIMIT:
                self._flush_history = self._flush_history[-FLUSH_HISTORY_LIMIT:]

    def get_stats(self) -> dict:
        """Метрики для мониторинга: buffer_size, events_processed, flush_count, flush_history."""
        return {
            "buffer_size": len(self._buffer),
            "buffer_size_max": self._buffer_size,
            "events_processed": self._events_processed,
            "flush_count": self._flush_count,
            "flush_history": list(self._flush_history),
        }

    async def process_quality_gate_event(
        self,
        event_data: dict,
        tenant_id: str,
        task_id: str | None = None,
    ) -> None:
        """
        Обрабатывает событие quality_gate.passed.
        Добавляет updates в буфер, flush при buffer_size или по таймеру.
        """
        artifact_id = event_data.get("artifact_id")
        dep_artifact_ids = event_data.get("dep_artifact_ids") or []

        if not artifact_id or not dep_artifact_ids:
            self.logger.debug(
                "quality_gate.passed skipped: missing artifact_id or dep_artifact_ids"
            )
            return

        task_id = task_id or event_data.get("task_id")
        updates_to_add = []
        for dep_id in dep_artifact_ids:
            updates_to_add.append({
                "tenant_id": tenant_id,
                "source_id": dep_id,
                "target_id": artifact_id,
                "score": 1.0,
            })

        async with self._lock:
            self._buffer.extend(updates_to_add)
            self._events_processed += len(updates_to_add)
            should_flush = len(self._buffer) >= self._buffer_size

        if should_flush:
            await self._flush()

    async def handle_quality_gate_passed(
        self,
        event_data: dict,
        tenant_id: str,
        task_id: str | None = None,
    ) -> None:
        """
        Точка входа: обработка quality_gate.passed.
        Вызывает process_quality_gate_event.
        """
        step_id = event_data.get("step_id", "")
        agent_type = event_data.get("agent_type", "")
        artefact_key = event_data.get("artefact_key", "")
        task_id = task_id or event_data.get("task_id")

        self.logger.debug(
            "quality_gate.passed: task_id=%s step_id=%s agent_type=%s artefact_key=%s tenant_id=%s",
            task_id,
            step_id,
            agent_type,
            artefact_key,
            tenant_id,
        )

        try:
            await self.process_quality_gate_event(event_data, tenant_id, task_id)
        except Exception as exc:
            self.logger.warning("process_quality_gate_event failed: %s", exc)
            if self._dlq_callback:
                try:
                    if asyncio.iscoroutinefunction(self._dlq_callback):
                        await self._dlq_callback(event_data, exc)
                    else:
                        self._dlq_callback(event_data, exc)
                except Exception as cb_exc:
                    self.logger.warning("DLQ callback failed: %s", cb_exc)
