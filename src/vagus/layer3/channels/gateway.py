"""
ChannelGateway — единая точка входа для каналов взаимодействия.

Создаёт задачу через API, ожидает завершения и возвращает результат.
"""

import asyncio
from typing import Any, Dict, Optional

import httpx

from ...layer0.logging import get_logger


class ChannelGateway:
    """
    Шлюз каналов: маршрутизирует запросы пользователей в API
    и возвращает результат выполнения задачи.
    """

    def __init__(self, api_url: str, api_key: str, timeout: int = 120):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.logger = get_logger("layer3.gateway")

    async def process_message(
        self,
        user_id: str,
        chat_id: str,
        prompt: str,
        task_type: str = "default",
    ) -> str:
        """
        Отправляет промпт в API, ожидает завершения задачи.

        Returns:
            Строка с результатом выполнения задачи.

        Raises:
            TimeoutError: если задача не завершилась за self.timeout секунд.
            RuntimeError: если задача завершилась с ошибкой или API недоступен.
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "user_id": user_id,
            "chat_id": chat_id,
            "prompt": prompt,
            "task_type": task_type,
        }

        async with httpx.AsyncClient(
            base_url=self.api_url,
            headers=headers,
            timeout=httpx.Timeout(self.timeout),
        ) as client:
            task_id = await self._create_task(client, payload)
            result = await self._wait_for_result(client, task_id)
            return result

    async def _create_task(
        self, client: httpx.AsyncClient, payload: Dict[str, Any]
    ) -> str:
        """POST /api/v1/tasks — создаёт задачу и возвращает task_id."""
        self.logger.info(
            f"Creating task for user={payload['user_id']} type={payload['task_type']}"
        )
        response = await client.post("/api/v1/tasks", json=payload)
        response.raise_for_status()
        data = response.json()
        task_id = data.get("task_id") or data.get("id")
        if not task_id:
            raise RuntimeError(f"API did not return task_id: {data}")
        self.logger.info(f"Task created: {task_id}")
        return task_id

    async def _wait_for_result(
        self,
        client: httpx.AsyncClient,
        task_id: str,
        poll_interval: float = 1.0,
    ) -> str:
        """
        GET /api/v1/tasks/{task_id} — поллинг до завершения.
        """
        elapsed = 0.0
        while elapsed < self.timeout:
            response = await client.get(f"/api/v1/tasks/{task_id}")
            response.raise_for_status()
            data = response.json()
            status = data.get("status", "")

            if status == "completed":
                result = data.get("result", "")
                if isinstance(result, dict):
                    return result.get("answer", result.get("text", str(result)))
                return str(result)

            if status == "failed":
                error = data.get("error", "Unknown error")
                raise RuntimeError(f"Task {task_id} failed: {error}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(
            f"Task {task_id} did not complete within {self.timeout}s"
        )
