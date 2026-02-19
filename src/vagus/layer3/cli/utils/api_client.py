"""
HTTP-клиент для CLI — обращается к REST API Vagus Asistent.
"""

from typing import Any, Dict, List, Optional

from .config import load_config

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


class CLIApiClient:
    """HTTP-клиент для CLI."""

    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        cfg = load_config()
        self.api_url = (api_url or cfg.get("api_url", "http://localhost:8000")).rstrip("/")
        self.api_key = api_key or cfg.get("api_key", "")

    @property
    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get(self, path: str) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed. pip install httpx")
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{self.api_url}{path}", headers=self._headers)
            resp.raise_for_status()
            return resp.json()

    def _post(self, path: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed. pip install httpx")
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{self.api_url}{path}", json=json_data, headers=self._headers)
            resp.raise_for_status()
            return resp.json()

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Аутентификация — возвращает токены."""
        return self._post("/api/v1/auth/token", {"username": username, "password": password})

    def create_task(self, prompt: str, task_type: str = "default") -> Dict[str, Any]:
        """Создаёт задачу."""
        return self._post("/api/v1/tasks", {"prompt": prompt, "task_type": task_type})

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Получает статус задачи."""
        return self._get(f"/api/v1/tasks/{task_id}")

    def list_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Список задач."""
        return self._get(f"/api/v1/tasks?limit={limit}")

    def get_agents(self) -> List[Dict[str, Any]]:
        """Список агентов."""
        return self._get("/api/v1/agents")

    def get_system_status(self) -> Dict[str, Any]:
        """Статус системы."""
        return self._get("/api/v1/status")
