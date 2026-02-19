"""
Меж-агентная коммуникация: asyncio.Queue (MVP) -> Redis (production).
"""

import asyncio
from collections import defaultdict
from typing import Any, Callable, Awaitable

from ...layer0.logging import get_logger


class CommunicationLayer:
    """
    Нервная система агентной системы.
    Pub/Sub по топикам + очередь результатов по task_id.
    """

    def __init__(self):
        self.topics: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.results: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self.subscribers: dict[str, list[Callable[[Any], Awaitable[None]]]] = defaultdict(list)
        self.logger = get_logger("layer2.communication")

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
