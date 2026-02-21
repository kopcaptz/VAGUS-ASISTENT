"""
TaskEventsWebSocket — WebSocket для real-time трансляции событий из Redis Streams.
Поддерживает task.planned, quality_gate.passed, agent.started (reflection).
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Optional

from fastapi import WebSocket

from vagus.layer0.logging import get_logger

logger = get_logger("layer3.api.websockets.task_events")

EVENT_TYPES = frozenset(
    ("task.planned", "quality_gate.passed", "agent.started", "reflection.triggered")
)


def _matches_task(message: dict, task_id: str) -> bool:
    """Проверяет, относится ли событие к заданному task_id (API UUID или plan_id)."""
    msg_task_id = message.get("task_id") or ""
    if msg_task_id == task_id:
        return True
    data = message.get("data")
    if isinstance(data, dict) and data.get("api_task_id") == task_id:
        return True
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            if isinstance(parsed, dict) and parsed.get("api_task_id") == task_id:
                return True
        except json.JSONDecodeError:
            pass
    return False


def _should_forward(event_type: str, data: dict) -> bool:
    """
    Фильтр по типу события.
    Поддерживаем: task.planned, quality_gate.passed, agent.started.
    agent.started с agent_type=reflection мапится в reflection.triggered при отправке.
    """
    return event_type in EVENT_TYPES


def _to_client_message(event_type: str, message: dict) -> dict:
    """Формирует JSON для отправки клиенту."""
    data = message.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data) if data else {}
        except json.JSONDecodeError:
            data = {}
    if event_type == "agent.started" and isinstance(data, dict) and data.get("agent_type") == "reflection":
        event_type = "reflection.triggered"
    return {
        "event": event_type,
        "task_id": message.get("task_id"),
        "data": data,
        "ts": message.get("ts"),
    }


class TaskEventsWebSocket:
    """
    WebSocket-хендлер для трансляции событий из Redis Streams.
    При подключении создаёт consumer group, читает события через xreadgroup,
    фильтрует по task_id и транслирует клиенту в JSON.
    """

    def __init__(
        self,
        websocket: WebSocket,
        task_id: str,
        redis_streams_client: Any,
        stream_name: str,
    ) -> None:
        self.websocket = websocket
        self.task_id = task_id
        self.redis_streams_client = redis_streams_client
        self.stream_name = stream_name
        self._shutdown = asyncio.Event()
        self._conn_id = uuid.uuid4().hex[:12]
        self._group_name = f"ws-task-{task_id}-{self._conn_id}"
        self._consumer_name = f"ws-{task_id}-{self._conn_id}"

    def _make_handler(self) -> Any:
        websocket = self.websocket
        task_id = self.task_id
        shutdown = self._shutdown

        async def handler(event_type: str, message: dict) -> None:
            if not _matches_task(message, task_id):
                return
            if not _should_forward(event_type, message.get("data") or {}):
                return
            payload = _to_client_message(event_type, message)
            try:
                await websocket.send_json(payload)
            except Exception as exc:
                logger.warning("TaskEventsWebSocket send failed for task_id=%s: %s", task_id, exc)
                shutdown.set()

        return handler

    async def run(self) -> None:
        """
        Основной цикл: запускает consumer и ожидает shutdown (disconnect).
        """
        handler = self._make_handler()
        await self.redis_streams_client.create_consumer_group(
            self.stream_name,
            self._group_name,
        )
        consumer_task = asyncio.create_task(
            self._consume_loop(handler),
        )
        disconnect_task = asyncio.create_task(self._wait_disconnect())
        done, _ = await asyncio.wait(
            [consumer_task, disconnect_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        self._shutdown.set()
        for t in (consumer_task, disconnect_task):
            if not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass

    async def _consume_loop(self, handler: Any) -> None:
        """Локальный цикл xreadgroup с вызовом handler и xack."""
        redis = self.redis_streams_client._redis
        block_ms = 2000

        while not self._shutdown.is_set():
            try:
                messages = await redis.xreadgroup(
                    groupname=self._group_name,
                    consumername=self._consumer_name,
                    streams={self.stream_name: ">"},
                    count=10,
                    block=block_ms,
                )
                if not messages:
                    continue
                for stream_key, stream_messages in messages:
                    for msg_id, raw_fields in stream_messages:
                        if isinstance(raw_fields, (list, tuple)):
                            raw_fields = dict(zip(raw_fields[::2], raw_fields[1::2]))
                        elif not isinstance(raw_fields, dict):
                            raw_fields = {}
                        event_type = raw_fields.get("event", "unknown")
                        data_raw = raw_fields.get("data", "{}")
                        try:
                            data = json.loads(data_raw) if isinstance(data_raw, str) else data_raw
                        except json.JSONDecodeError:
                            data = {}
                        message = {
                            "event": event_type,
                            "task_id": raw_fields.get("task_id"),
                            "data": data,
                            "ts": raw_fields.get("ts"),
                        }
                        try:
                            await handler(event_type, message)
                            await redis.xack(stream_key, self._group_name, msg_id)
                        except Exception as exc:
                            logger.debug("TaskEventsWebSocket handler error: %s", exc)
                            if self._shutdown.is_set():
                                return
                            await redis.xack(stream_key, self._group_name, msg_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._shutdown.is_set():
                    return
                logger.warning("TaskEventsWebSocket consume loop error: %s", exc)
                await asyncio.sleep(1)

    async def _wait_disconnect(self) -> None:
        """Ожидает отключение клиента."""
        try:
            while not self._shutdown.is_set():
                msg = await self.websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    self._shutdown.set()
                    return
        except Exception:
            self._shutdown.set()
