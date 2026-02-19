"""
CLI client for Vagus Asistent.
Provides login, task creation, and status checking.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx


DEFAULT_CONFIG_PATH = Path.home() / ".vagus" / "config.json"
DEFAULT_BASE_URL = "http://localhost:8000"


@dataclass
class VagusCLI:
    """Command-line client for Vagus API."""

    base_url: str = DEFAULT_BASE_URL
    config_path: Path = DEFAULT_CONFIG_PATH
    _token: Optional[str] = field(default=None, repr=False)
    _http: Optional[httpx.Client] = field(default=None, repr=False)

    def _client(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(base_url=self.base_url, timeout=30)
        return self._http

    def login(self, username: str, password: str) -> dict[str, Any]:
        resp = self._client().post("/auth/token", json={"username": username, "password": password})
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._save_config(data)
        return data

    def create_task(self, prompt: str, task_type: str = "default") -> dict[str, Any]:
        self._ensure_token()
        resp = self._client().post(
            "/tasks",
            json={"prompt": prompt, "task_type": task_type},
            headers={"Authorization": f"Bearer {self._token}"},
        )
        resp.raise_for_status()
        return resp.json()

    def get_status(self, task_id: str) -> dict[str, Any]:
        resp = self._client().get(f"/tasks/{task_id}")
        resp.raise_for_status()
        return resp.json()

    def _ensure_token(self) -> None:
        if self._token:
            return
        config = self._load_config()
        if config and "access_token" in config:
            self._token = config["access_token"]
        else:
            raise RuntimeError("Not logged in. Run login() first.")

    def _save_config(self, data: dict[str, Any]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(data, indent=2))

    def _load_config(self) -> Optional[dict[str, Any]]:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text())
        return None
