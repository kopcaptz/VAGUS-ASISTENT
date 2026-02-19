"""
Dashboard client for Vagus Asistent.
Wraps API calls for the monitoring / management UI.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

import httpx


@dataclass
class DashboardClient:
    """HTTP-based dashboard client that talks to the Vagus API."""

    base_url: str = "http://localhost:8000"
    _token: Optional[str] = field(default=None, repr=False)
    _http: Optional[httpx.Client] = field(default=None, repr=False)

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(base_url=self.base_url, timeout=30)
        return self._http

    def _headers(self) -> dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    def login(self, username: str, password: str) -> dict[str, Any]:
        resp = self._client().post("/auth/token", json={"username": username, "password": password})
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        return data

    def create_task(self, prompt: str, task_type: str = "default") -> dict[str, Any]:
        if not self._token:
            raise RuntimeError("Not authenticated")
        resp = self._client().post(
            "/tasks",
            json={"prompt": prompt, "task_type": task_type},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    def get_metrics(self) -> dict[str, Any]:
        if not self._token:
            raise RuntimeError("Not authenticated")
        resp = self._client().get("/dashboard/metrics", headers=self._headers())
        resp.raise_for_status()
        return resp.json()
