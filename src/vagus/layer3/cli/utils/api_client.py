"""
HTTP client for the CLI interface.
All requests go through the REST API.
"""

from typing import Any, Dict, List, Optional

import httpx

from .config import get_api_key, get_api_url


class CLIApiClient:
    """Synchronous HTTP client for CLI commands."""

    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        self.api_url = (api_url or get_api_url()).rstrip("/")
        self.api_key = api_key or get_api_key()

    @property
    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticates and returns token response."""
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{self.api_url}/api/v1/auth/token",
                data={"username": username, "password": password},
            )
        resp.raise_for_status()
        return resp.json()

    def create_task(self, prompt: str, task_type: str = "default") -> Dict[str, Any]:
        """Creates a new task."""
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{self.api_url}/api/v1/tasks",
                json={"prompt": prompt, "task_type": task_type},
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Gets task status."""
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{self.api_url}/api/v1/tasks/{task_id}",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def list_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Lists recent tasks."""
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{self.api_url}/api/v1/tasks",
                params={"limit": limit},
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json().get("tasks", [])

    def get_agents(self) -> List[Dict[str, Any]]:
        """Lists available agents."""
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{self.api_url}/api/v1/agents",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_system_status(self) -> Dict[str, Any]:
        """Gets system status."""
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{self.api_url}/api/v1/status",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()
