"""
Channel Gateway — adapter between chat platforms and the REST API.
Translates chat messages into API calls and returns results.
"""

import asyncio
from typing import Optional

import httpx


class ChannelGateway:
    """
    Gateway between chat channels (Telegram, Discord) and the Vagus REST API.
    Purely a transport layer with no business logic.
    """

    def __init__(self, api_url: str, api_key: str, timeout: int = 120):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def process_message(
        self,
        user_id: str,
        chat_id: str,
        prompt: str,
        task_type: str = "default",
    ) -> str:
        """
        Creates a task via the API and waits for completion.
        Returns the result as a string.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            create_resp = await client.post(
                f"{self.api_url}/api/v1/tasks",
                json={
                    "prompt": prompt,
                    "task_type": task_type,
                    "metadata": {"user_id": user_id, "chat_id": chat_id},
                },
                headers=self._headers,
            )
            create_resp.raise_for_status()
            task_data = create_resp.json()
            task_id = task_data["task_id"]

            for _ in range(self.timeout * 2):
                await asyncio.sleep(0.5)
                status_resp = await client.get(
                    f"{self.api_url}/api/v1/tasks/{task_id}",
                    headers=self._headers,
                )
                status_resp.raise_for_status()
                status_data = status_resp.json()

                if status_data["status"] == "completed":
                    result = status_data.get("result", {})
                    if isinstance(result, dict):
                        return result.get("content", str(result))
                    return str(result)
                elif status_data["status"] == "failed":
                    raise RuntimeError(status_data.get("error", "Task failed"))

        raise TimeoutError(f"Task {task_id} did not complete within {self.timeout}s")

    async def get_status(self) -> dict:
        """Checks API availability."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.api_url}/health")
            resp.raise_for_status()
            return resp.json()
