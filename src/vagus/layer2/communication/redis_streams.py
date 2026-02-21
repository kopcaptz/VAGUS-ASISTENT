"""
Redis Streams client for Event Bus with guaranteed delivery.
Consumer Groups, ACK, and Dead-Letter Queue support.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Awaitable, Callable, Optional

from ...layer0.logging import get_logger

DEFAULT_STREAM_NAME = "vagus:events:stream"
RETRY_KEY_PREFIX = "vagus:stream:retries:"


class RedisStreamsClient:
    """
    Redis Streams client for Event Bus.
    Supports publish_event, Consumer Groups, process_events with ACK, and DLQ.
    """

    def __init__(
        self,
        redis_url: str,
        *,
        stream_name: str = DEFAULT_STREAM_NAME,
        maxlen: int = 10000,
    ) -> None:
        try:
            import redis.asyncio as redis  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError("redis package is not available") from exc
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._stream_name = stream_name
        self._maxlen = maxlen
        self.logger = get_logger("layer2.communication.redis_streams")

    async def publish_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        task_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Публикует событие в Redis Stream через XADD.
        Возвращает message ID или None при ошибке.
        """
        if tenant_id is not None:
            payload = {**payload, "tenant_id": tenant_id}

        message = {
            "event": event_type,
            "task_id": task_id or "",
            "data": json.dumps(payload, ensure_ascii=False, default=str),
            "ts": str(time.time()),
        }

        # redis-py xadd expects flat field/value pairs
        fields: dict[str, str] = {}
        for k, v in message.items():
            fields[k] = str(v) if not isinstance(v, str) else v

        try:
            msg_id = await self._redis.xadd(
                self._stream_name,
                fields,
                id="*",
                maxlen=self._maxlen,
                approximate=True,
            )
            self.logger.debug("Event published to stream: %s %s task_id=%s", event_type, msg_id, task_id)
            return msg_id
        except Exception as exc:
            self.logger.warning("Failed to publish event to Redis Stream: %s", exc)
            return None

    async def create_consumer_group(
        self,
        stream_name: str,
        group_name: str,
    ) -> bool:
        """
        Создаёт consumer group если не существует.
        XGROUP CREATE stream group $ MKSTREAM.
        Возвращает True при успехе.
        """
        try:
            await self._redis.xgroup_create(
                stream_name,
                group_name,
                id="$",
                mkstream=True,
            )
            self.logger.info("Created consumer group %s on stream %s", group_name, stream_name)
            return True
        except Exception as exc:
            err_msg = str(exc).lower()
            if "busygroup" in err_msg or "already exists" in err_msg:
                self.logger.debug("Consumer group %s already exists on %s", group_name, stream_name)
                return True
            self.logger.warning("Failed to create consumer group %s: %s", group_name, exc)
            return False

    async def move_to_dlq(
        self,
        stream_name: str,
        message_id: str,
        raw_data: dict[str, Any],
        error_msg: str,
    ) -> None:
        """
        Перемещает сообщение в Dead-Letter Queue.
        XADD в {stream_name}_dlq с original_id, error, payload, ts.
        """
        dlq_name = f"{stream_name}_dlq"
        fields = {
            "original_id": message_id,
            "error": error_msg,
            "payload": json.dumps(raw_data, ensure_ascii=False, default=str),
            "ts": str(time.time()),
        }
        try:
            await self._redis.xadd(dlq_name, fields, id="*", maxlen=10000, approximate=True)
            self.logger.warning("Moved message %s to DLQ %s: %s", message_id, dlq_name, error_msg)
        except Exception as exc:
            self.logger.error("Failed to move message to DLQ: %s", exc)

    async def process_events(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        handler: Callable[[str, dict], Awaitable[None]],
        *,
        max_retries: int = 3,
        block_ms: int = 5000,
        _shutdown: Optional[asyncio.Event] = None,
    ) -> None:
        """
        Цикл обработки событий: XREADGROUP BLOCK, вызов handler, XACK при успехе.
        При ошибке > max_retries раз — move_to_dlq и XACK.
        """
        await self.create_consumer_group(stream_name, group_name)

        shutdown = _shutdown or asyncio.Event()

        while not shutdown.is_set():
            try:
                # XREADGROUP GROUP group_name consumer_name STREAMS stream_name >
                messages = await self._redis.xreadgroup(
                    groupname=group_name,
                    consumername=consumer_name,
                    streams={stream_name: ">"},
                    count=10,
                    block=block_ms,
                )

                if not messages:
                    continue

                for stream_key, stream_messages in messages:
                    for msg_id, raw_fields in stream_messages:
                        # redis-py may return raw_fields as list [k1,v1,k2,v2]; convert to dict
                        if isinstance(raw_fields, (list, tuple)):
                            raw_fields = dict(zip(raw_fields[::2], raw_fields[1::2]))
                        elif not isinstance(raw_fields, dict):
                            raw_fields = {}

                        retry_key = f"{RETRY_KEY_PREFIX}{msg_id}"

                        try:
                            # Parse message
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

                            await handler(event_type, message)
                            await self._redis.xack(stream_key, group_name, msg_id)
                            await self._redis.delete(retry_key)

                        except Exception as exc:
                            retries = 0
                            try:
                                retries = int(await self._redis.incr(retry_key))
                                await self._redis.expire(retry_key, 86400)  # 24h TTL
                            except Exception:
                                pass

                            if retries >= max_retries:
                                full_raw = dict(raw_fields) if isinstance(raw_fields, dict) else {}
                                await self.move_to_dlq(
                                    stream_key,
                                    msg_id,
                                    {"event": raw_fields.get("event"), "data": raw_fields.get("data"), **full_raw},
                                    str(exc),
                                )
                                await self._redis.xack(stream_key, group_name, msg_id)
                                await self._redis.delete(retry_key)
                                self.logger.warning(
                                    "Message %s failed %d times, moved to DLQ: %s",
                                    msg_id,
                                    retries,
                                    exc,
                                )
                            else:
                                self.logger.debug(
                                    "Message %s processing failed (attempt %d/%d), will retry: %s",
                                    msg_id,
                                    retries,
                                    max_retries,
                                    exc,
                                )

            except asyncio.CancelledError:
                self.logger.info("process_events cancelled for group %s", group_name)
                raise
            except Exception as exc:
                self.logger.warning("process_events error, reconnecting: %s", exc)
                await asyncio.sleep(1)

    def start_stream_consumer(
        self,
        stream_name: str,
        group_name: str,
        consumer_name: str,
        handler: Callable[[str, dict], Awaitable[None]],
        *,
        max_retries: int = 3,
        block_ms: int = 5000,
    ) -> tuple[asyncio.Task[None], asyncio.Event]:
        """
        Запускает process_events в фоновой задаче.
        Возвращает (task, shutdown_event) для отмены при shutdown.
        """
        shutdown = asyncio.Event()
        task = asyncio.create_task(
            self.process_events(
                stream_name,
                group_name,
                consumer_name,
                handler,
                max_retries=max_retries,
                block_ms=block_ms,
                _shutdown=shutdown,
            ),
        )
        return task, shutdown

    async def close(self) -> None:
        """Закрывает Redis соединение."""
        try:
            await self._redis.aclose()
            self.logger.debug("Redis Streams connection closed")
        except Exception as exc:
            self.logger.debug("Error closing Redis Streams: %s", exc)
