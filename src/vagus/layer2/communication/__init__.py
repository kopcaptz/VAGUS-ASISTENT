"""
Меж-агентная коммуникация: asyncio.Queue (MVP) -> Redis (production).
Event Bus: Redis Pub/Sub, Redis Streams, или in-memory fallback.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from typing import Any, Callable, Awaitable, List, Optional

from ...layer0.logging import get_logger
from .blackboard import SharedBlackboard

CHANNEL_SYSTEM = "vagus:events:system"
CHANNEL_TASK_PREFIX = "vagus:events:task:"


def create_communication_from_config(layer2_config: Optional[dict]) -> "CommunicationLayer":
    """
    Создаёт CommunicationLayer из конфигурации layer2.
    Читает layer2.communication.redis_url, event_bus.enabled, event_bus.use_streams.
    """
    comm_cfg = (layer2_config or {}).get("communication") or {}
    if not isinstance(comm_cfg, dict):
        return CommunicationLayer()
    redis_url = comm_cfg.get("redis_url")
    event_bus_cfg = comm_cfg.get("event_bus") or {}
    if isinstance(event_bus_cfg, dict):
        event_bus_enabled = event_bus_cfg.get("enabled", True)
        use_streams = event_bus_cfg.get("use_streams", False)
        stream_name = event_bus_cfg.get("stream_name", "vagus:events:stream")
        max_retries = event_bus_cfg.get("max_retries", 3)
    else:
        event_bus_enabled = True
        use_streams = False
        stream_name = "vagus:events:stream"
        max_retries = 3
    return CommunicationLayer(
        redis_url=redis_url if redis_url else None,
        event_bus_enabled=event_bus_enabled,
        use_streams=use_streams,
        stream_name=stream_name,
        max_retries=max_retries,
    )


class CommunicationLayer:
    """
    Нервная система агентной системы.
    Pub/Sub по топикам + очередь результатов по task_id.
    Event Bus: Redis Streams, Redis Pub/Sub, или in-memory (callbacks).
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        *,
        event_bus_enabled: bool = True,
        use_streams: bool = False,
        stream_name: str = "vagus:events:stream",
        max_retries: int = 3,
    ) -> None:
        self.topics: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.results: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.subscribers: dict[str, list[Callable[[Any], Awaitable[None]]]] = defaultdict(list)
        self.event_subscribers: list[Callable[[str, dict], Awaitable[None]]] = []
        self.logger = get_logger("layer2.communication")
        self._redis_url = redis_url
        self._event_bus_enabled = event_bus_enabled
        self._use_streams = use_streams
        self._stream_name = stream_name
        self._max_retries = max_retries
        self._redis = None
        self._redis_initialized = False
        self._streams_client: Optional[Any] = None

        if redis_url and event_bus_enabled:
            if use_streams:
                try:
                    from .redis_streams import RedisStreamsClient
                    self._streams_client = RedisStreamsClient(
                        redis_url,
                        stream_name=stream_name,
                    )
                    self._redis_initialized = True
                    self.logger.info(
                        "Event Bus using Redis Streams: %s stream=%s",
                        redis_url[:50] if len(redis_url) > 50 else redis_url,
                        stream_name,
                    )
                except Exception as exc:
                    self.logger.warning("Redis Streams unavailable, fallback to in-memory: %s", exc)
                    self._streams_client = None
                    self._redis_initialized = False
            else:
                try:
                    import redis.asyncio as redis  # type: ignore[import-untyped]
                    self._redis = redis.from_url(redis_url, decode_responses=True)
                    self._redis_initialized = True
                    self.logger.info(
                        "Event Bus using Redis Pub/Sub: %s",
                        redis_url[:50] if len(redis_url) > 50 else redis_url,
                    )
                except Exception as exc:
                    self.logger.warning("Redis Event Bus unavailable, fallback to in-memory: %s", exc)
                    self._redis = None
                    self._redis_initialized = False
        elif not event_bus_enabled:
            self.logger.debug("Event Bus disabled")
        else:
            self.logger.debug("Event Bus using in-memory backend")

    @property
    def uses_streams(self) -> bool:
        """True если Event Bus использует Redis Streams."""
        return bool(self._streams_client and self._redis_initialized)

    async def publish_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        task_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        """
        Публикует событие в Event Bus.
        tenant_id включается в payload для TenantContext.
        При redis_url: публикует в vagus:events:system и vagus:events:task:{task_id}.
        При in-memory: вызывает подписчиков event_subscribers.
        При event_bus_enabled=False: no-op.
        """
        if not self._event_bus_enabled:
            return

        if tenant_id is not None:
            payload = {**payload, "tenant_id": tenant_id}

        message = {
            "event": event_type,
            "task_id": task_id,
            "data": payload,
            "ts": time.time(),
        }

        if self._streams_client and self._redis_initialized:
            await self._streams_client.publish_event(
                event_type,
                payload,
                task_id=task_id,
                tenant_id=tenant_id,
            )
        elif self._redis and self._redis_initialized:
            try:
                raw = json.dumps(message, ensure_ascii=False, default=str)
                await self._redis.publish(CHANNEL_SYSTEM, raw)
                self.logger.debug("Event published: %s task_id=%s", event_type, task_id)
                if task_id:
                    await self._redis.publish(f"{CHANNEL_TASK_PREFIX}{task_id}", raw)
            except Exception as exc:
                self.logger.warning("Failed to publish event to Redis: %s", exc)
        else:
            self.logger.debug("Event published: %s task_id=%s", event_type, task_id)
            await self.publish(CHANNEL_SYSTEM, message)
            if task_id:
                await self.publish(f"{CHANNEL_TASK_PREFIX}{task_id}", message)
            for callback in self.event_subscribers:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event_type, message)
                    else:
                        callback(event_type, message)
                except Exception as exc:
                    self.logger.warning("Event subscriber callback error: %s", exc)

    def subscribe_to_events(
        self,
        callback: Callable[[str, dict], Awaitable[None]],
        channels: Optional[List[str]] = None,
    ) -> None:
        """
        Подписывает колбэк на события.
        In-memory: callback вызывается при publish_event.
        Redis: запускает фоновый listen (вызов subscribe_to_events_redis отдельно).
        """
        self.event_subscribers.append(callback)
        self.logger.debug("Subscribed to events (in-memory)")

    def start_stream_consumer(
        self,
        group_name: str,
        consumer_name: str,
        handler: Callable[[str, dict], Awaitable[None]],
    ) -> tuple[asyncio.Task[None], asyncio.Event]:
        """
        Запускает consumer для Redis Streams. Только при use_streams=True.
        Возвращает (task, shutdown_event).
        """
        if not self._streams_client or not self._redis_initialized:
            self.logger.warning("start_stream_consumer called but Redis Streams not available")
            shutdown = asyncio.Event()
            return asyncio.create_task(asyncio.sleep(0)), shutdown
        return self._streams_client.start_stream_consumer(
            self._stream_name,
            group_name,
            consumer_name,
            handler,
            max_retries=self._max_retries,
        )

    async def subscribe_to_events_redis(
        self,
        callback: Callable[[str, dict], Awaitable[None]],
        channels: Optional[List[str]] = None,
    ) -> asyncio.Task[None]:
        """
        Подписка на Redis каналы (Pub/Sub). Запускает фоновую задачу listen.
        Для Redis Streams используйте start_stream_consumer.
        Возвращает Task для отмены при shutdown.
        """
        if not self._redis or not self._redis_initialized:
            self.logger.warning("subscribe_to_events_redis called but Redis Pub/Sub not available")
            return asyncio.create_task(asyncio.sleep(0))

        target_channels = channels or [CHANNEL_SYSTEM]
        pubsub = self._redis.pubsub()

        async def _listen() -> None:
            while True:
                try:
                    await pubsub.subscribe(*target_channels)
                    self.logger.debug("Subscribed to Redis channels: %s", target_channels)
                    async for msg in pubsub.listen():
                        if msg["type"] == "message":
                            try:
                                data = json.loads(msg["data"])
                                event_type = data.get("event", "unknown")
                                if asyncio.iscoroutinefunction(callback):
                                    await callback(event_type, data)
                                else:
                                    callback(event_type, data)
                            except (json.JSONDecodeError, KeyError) as e:
                                self.logger.debug("Invalid event message: %s", e)
                except (ConnectionError, OSError) as exc:
                    self.logger.warning("Event Bus Redis connection lost: %s", exc)
                    try:
                        await self._redis.ping()
                        self.logger.info("Event Bus reconnected to Redis")
                    except Exception:
                        await asyncio.sleep(1)

        return asyncio.create_task(_listen())

    async def close(self) -> None:
        """Закрывает Redis соединения."""
        if self._streams_client:
            try:
                await self._streams_client.close()
                self.logger.debug("Event Bus Redis Streams connection closed")
            except Exception as exc:
                self.logger.debug("Error closing Redis Streams: %s", exc)
            finally:
                self._streams_client = None
                self._redis_initialized = False
        if self._redis:
            try:
                await self._redis.aclose()
                self.logger.debug("Event Bus Redis connection closed")
            except Exception as exc:
                self.logger.debug("Error closing Redis: %s", exc)
            finally:
                self._redis = None
                self._redis_initialized = False

    async def publish(self, topic: str, message: dict[str, Any]) -> None:
        """Публикует сообщение в топик. Вызывает колбэки подписчиков."""
        callbacks = self.subscribers.get(topic, [])
        for callback in callbacks:
            asyncio.create_task(callback(message))
        self.logger.debug(f"Published to {topic}: {len(callbacks)} subscribers")

    async def subscribe(self, topic: str, callback: Callable[[Any], Awaitable[None]]) -> None:
        """Подписывает колбэк на топик."""
        self.subscribers[topic].append(callback)
        self.logger.debug(f"Subscribed to {topic}")

    async def publish_result(self, task_id: str, result: Any) -> None:
        """Помещает результат задачи в очередь для task_id."""
        if task_id not in self.results:
            self.results[task_id] = asyncio.Queue()
        await self.results[task_id].put(result)
        self.logger.debug(f"Result published for task {task_id}")

    async def subscribe_to_result(self, task_id: str, timeout: int = 300) -> Any:
        """Ждёт результат задачи. При таймауте возвращает dict с error."""
        try:
            if task_id not in self.results:
                self.results[task_id] = asyncio.Queue()
            return await asyncio.wait_for(self.results[task_id].get(), timeout=timeout)
        except asyncio.TimeoutError:
            self.logger.warning(f"Task {task_id} timed out after {timeout}s")
            return {"error": f"Task {task_id} timed out"}
