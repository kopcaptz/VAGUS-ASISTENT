"""
ChannelGateway — шлюз между чат-каналами и REST API.
"""

import asyncio
from typing import Optional

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class ChannelGateway:
    """
    Транслирует сообщения из чат-каналов в вызовы REST API
    и возвращает результаты.
    """

    def __init__(
        self,
        api_url: str,
        api_key: str = "",
        *,
        username: str = "",
        password: str = "",
        timeout: int = 120,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key.strip()
        self.username = username.strip()
        self.password = password
        self.timeout = timeout
        self._token: Optional[str] = self.api_key or None

    async def _auth_headers(self, client: "httpx.AsyncClient") -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        if not self.username or not self.password:
            raise RuntimeError(
                "Telegram gateway credentials are not configured. "
                "Set VAGUS_BOT_USERNAME/VAGUS_BOT_PASSWORD or VAGUS_API_KEY."
            )
        auth_resp = await client.post(
            f"{self.api_url}/api/v1/auth/token",
            json={"username": self.username, "password": self.password},
        )
        auth_resp.raise_for_status()
        token = str(auth_resp.json().get("access_token", "")).strip()
        if not token:
            raise RuntimeError("Auth token is empty")
        self._token = token
        return {"Authorization": f"Bearer {self._token}"}

    async def process_message(
        self,
        user_id: str,
        chat_id: str,
        prompt: str,
        task_type: str = "default",
    ) -> str:
        """
        Создаёт задачу через API и ожидает выполнения.
        Возвращает строку с результатом.
        """
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed. pip install httpx")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = await self._auth_headers(client)
            create_resp = await client.post(
                f"{self.api_url}/api/v1/tasks",
                json={
                    "prompt": prompt,
                    "task_type": task_type,
                    "metadata": {"user_id": user_id, "chat_id": chat_id},
                },
                headers=headers,
            )
            if create_resp.status_code == 401 and self.username and self.password:
                self._token = None
                headers = await self._auth_headers(client)
                create_resp = await client.post(
                    f"{self.api_url}/api/v1/tasks",
                    json={
                        "prompt": prompt,
                        "task_type": task_type,
                        "metadata": {"user_id": user_id, "chat_id": chat_id},
                    },
                    headers=headers,
                )
            create_resp.raise_for_status()
            task_data = create_resp.json()
            task_id = task_data["task_id"]

            for _ in range(self.timeout * 2):
                await asyncio.sleep(0.5)
                status_resp = await client.get(
                    f"{self.api_url}/api/v1/tasks/{task_id}",
                    headers=headers,
                )
                if status_resp.status_code == 401 and self.username and self.password:
                    self._token = None
                    headers = await self._auth_headers(client)
                    status_resp = await client.get(
                        f"{self.api_url}/api/v1/tasks/{task_id}",
                        headers=headers,
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

    async def health_check(self) -> bool:
        """Проверяет доступность API."""
        if not HTTPX_AVAILABLE:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.api_url}/health")
                return resp.status_code == 200
        except Exception:
            return False
