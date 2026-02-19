"""
HTTP клиент для API Vagus Asistent.
Использует api_url и api_key из ~/.vagus/config.json.
"""

from typing import Any, Dict, List, Optional

import httpx

from .config import load_config


class CLIApiClient:
    """Клиент для работы с Vagus API из CLI."""

    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        config = load_config()
        self.api_url = api_url or config.get("api_url", "http://localhost:8000")
        self.api_key = api_key or config.get("api_key", "")
        self.base_url = self.api_url.rstrip("/")

    def _headers(self) -> Dict[str, str]:
        """Заголовки с Authorization."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def create_task(self, prompt: str, task_type: str = "default") -> Dict[str, Any]:
        """Создаёт задачу через POST /api/v1/tasks."""
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self.base_url}/api/v1/tasks",
                json={"prompt": prompt, "task_type": task_type},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Получает статус задачи через GET /api/v1/tasks/{task_id}."""
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{self.base_url}/api/v1/tasks/{task_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    def list_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получает список задач через GET /api/v1/tasks."""
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"{self.base_url}/api/v1/tasks",
                params={"limit": limit},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()
