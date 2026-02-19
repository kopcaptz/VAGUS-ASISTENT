"""
HTTP-клиент для Dashboard — обращается к REST API Vagus Asistent.
"""

from typing import Any, Dict, List, Optional

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

API_BASE_URL = "http://localhost:8000/api/v1"


class VagusAPIClient:
    """HTTP-клиент для Dashboard."""

    def __init__(self, base_url: str = API_BASE_URL, token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self._token = token

    @property
    def root_url(self) -> str:
        if self.base_url.endswith("/api/v1"):
            return self.base_url[: -len("/api/v1")]
        return self.base_url

    @property
    def _headers(self) -> Dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    def login(self, username: str, password: str) -> bool:
        """Аутентификация — сохраняет токен."""
        if not HTTPX_AVAILABLE:
            return False
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"{self.base_url}/auth/token",
                    json={"username": username, "password": password},
                )
            if resp.status_code == 200:
                data = resp.json()
                self._token = data.get("access_token", "")
                return True
        except Exception:
            pass
        return False

    def create_task(self, prompt: str, task_type: str = "default") -> Dict[str, Any]:
        """Создать задачу."""
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{self.base_url}/tasks",
                json={"prompt": prompt, "task_type": task_type},
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Статус задачи."""
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{self.base_url}/tasks/{task_id}",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def list_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Список задач."""
        if not HTTPX_AVAILABLE:
            return []
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{self.base_url}/tasks?limit={limit}",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_agents(self) -> List[Dict[str, Any]]:
        """Список агентов."""
        if not HTTPX_AVAILABLE:
            return []
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{self.base_url}/agents",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_system_status(self) -> Dict[str, Any]:
        """Статус системы."""
        if not HTTPX_AVAILABLE:
            return {}
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{self.base_url}/status",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_prometheus_metrics(self) -> str:
        """Текст метрик Prometheus."""
        if not HTTPX_AVAILABLE:
            return ""
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{self.root_url}/metrics",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.text

    def get_detailed_health(self) -> Dict[str, Any]:
        """Детальный health check."""
        if not HTTPX_AVAILABLE:
            return {}
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                f"{self.root_url}/health/detailed",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()
