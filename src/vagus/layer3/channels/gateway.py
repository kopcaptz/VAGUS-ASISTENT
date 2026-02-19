"""
Gateway — единая точка входа для каналов.
Маршрутизация сообщений между клиентами и внутренними сервисами.
"""

import asyncio
import json
from typing import Any, Dict

import httpx


class ChannelGateway:
    """Шлюз для обработки сообщений через Vagus API."""

    def __init__(self, api_url: str, api_key: str, timeout: int = 120):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        """Заголовки с Authorization."""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    async def process_message(
        self,
        user_id: str,
        chat_id: str,
        prompt: str,
        task_type: str = "default",
    ) -> str:
        """
        Создаёт задачу, ожидает завершения, возвращает результат.
        Raises httpx.HTTPStatusError при ошибках API.
        """
        async with httpx.AsyncClient(timeout=float(self.timeout)) as client:
            resp = await client.post(
                f"{self.api_url}/api/v1/tasks",
                json={"prompt": prompt, "task_type": task_type},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        task_id = data["task_id"]
        poll_interval = 0.5
        elapsed = 0.0

        async with httpx.AsyncClient(timeout=30.0) as client:
            while elapsed < self.timeout:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                status_resp = await client.get(
                    f"{self.api_url}/api/v1/tasks/{task_id}",
                    headers=self._headers(),
                )
                status_resp.raise_for_status()
                status_data = status_resp.json()

                status = status_data.get("status", "")

                if status == "completed":
                    result = status_data.get("result")
                    if result is None:
                        return "Задача выполнена."
                    if isinstance(result, str):
                        return result
                    if isinstance(result, dict):
                        return json.dumps(result, ensure_ascii=False, indent=2)
                    return str(result)

                if status == "failed":
                    error = status_data.get("error", "Unknown error")
                    raise RuntimeError(f"Задача не выполнена: {error}")

        raise TimeoutError(f"Таймаут {self.timeout}с при ожидании задачи {task_id}")
