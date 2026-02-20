"""
HTTP-клиент для CLI — обращается к REST API Vagus Asistent.
"""

import json
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional

from vagus.logging import generate_request_id, generate_trace_id, get_trace_id
from vagus.layer3.security.request_signing import (
    HEADER_CLIENT_ID,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    create_request_signature,
    load_or_create_client_credentials,
)

from .config import load_config

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


@lru_cache(maxsize=1)
def _load_config_cached() -> dict[str, Any]:
    return load_config()


class CLIApiClient:
    """HTTP-клиент для CLI."""

    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        cfg = _load_config_cached()
        self.api_url = (api_url or cfg.get("api_url", "http://localhost:8000")).rstrip("/")
        self.api_key = api_key or cfg.get("api_key", "")
        self.trace_id = get_trace_id() or generate_trace_id()
        self.enable_request_signing = bool(cfg.get("enable_request_signing", True))
        self._client_credentials: Optional[dict[str, str]] = None

    def _get_client_credentials(self) -> Optional[dict[str, str]]:
        if self._client_credentials is None and self.enable_request_signing:
            self._client_credentials = load_or_create_client_credentials()
        return self._client_credentials

    @property
    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"User-Agent": "vagus-cli/1.0"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_request_headers(
        self,
        *,
        method: str,
        path: str,
        body_bytes: bytes,
        cli_command: str,
        cli_arguments: Optional[dict[str, Any]],
    ) -> Dict[str, str]:
        headers = dict(self._headers)
        headers["X-Trace-Id"] = self.trace_id
        headers["X-Request-Id"] = generate_request_id()
        headers["X-Vagus-CLI-Command"] = cli_command
        if cli_arguments:
            headers["X-Vagus-CLI-Arguments"] = json.dumps(cli_arguments, ensure_ascii=False)

        credentials = self._get_client_credentials()
        if self.enable_request_signing and credentials:
            timestamp = str(int(time.time()))
            signature = create_request_signature(
                secret=credentials["client_secret"],
                method=method,
                path=path,
                timestamp=timestamp,
                body=body_bytes,
                client_id=credentials["client_id"],
            )
            headers[HEADER_CLIENT_ID] = credentials["client_id"]
            headers[HEADER_TIMESTAMP] = timestamp
            headers[HEADER_SIGNATURE] = signature

        return headers

    def _get(
        self,
        path: str,
        *,
        cli_command: str,
        cli_arguments: Optional[dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed. pip install httpx")
        headers = self._build_request_headers(
            method="GET",
            path=path,
            body_bytes=b"",
            cli_command=cli_command,
            cli_arguments=cli_arguments,
        )
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{self.api_url}{path}", headers=headers)
            resp.raise_for_status()
            return resp.json()

    def _post(
        self,
        path: str,
        json_data: Dict[str, Any],
        *,
        cli_command: str,
        cli_arguments: Optional[dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed. pip install httpx")
        body_bytes = json.dumps(json_data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = self._build_request_headers(
            method="POST",
            path=path,
            body_bytes=body_bytes,
            cli_command=cli_command,
            cli_arguments=cli_arguments,
        )
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{self.api_url}{path}", json=json_data, headers=headers)
            resp.raise_for_status()
            return resp.json()

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Аутентификация — возвращает токены."""
        return self._post(
            "/api/v1/auth/token",
            {"username": username, "password": password},
            cli_command="auth.login",
            cli_arguments={"username": username},
        )

    def create_task(self, prompt: str, task_type: str = "default") -> Dict[str, Any]:
        """Создаёт задачу."""
        return self._post(
            "/api/v1/tasks",
            {"prompt": prompt, "task_type": task_type},
            cli_command="task.create",
            cli_arguments={"task_type": task_type},
        )

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Получает статус задачи."""
        return self._get(
            f"/api/v1/tasks/{task_id}",
            cli_command="task.status",
            cli_arguments={"task_id": task_id},
        )

    def list_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Список задач."""
        return self._get(
            f"/api/v1/tasks?limit={limit}",
            cli_command="task.list",
            cli_arguments={"limit": limit},
        )

    def get_agents(self) -> List[Dict[str, Any]]:
        """Список агентов."""
        return self._get("/api/v1/agents", cli_command="agent.list")

    def get_system_status(self) -> Dict[str, Any]:
        """Статус системы."""
        return self._get("/api/v1/status", cli_command="admin.status")

    def list_api_keys(self) -> List[Dict[str, Any]]:
        """Возвращает список API ключей."""
        payload = self._get("/api/v1/keys", cli_command="keys.list")
        keys = payload.get("keys", []) if isinstance(payload, dict) else []
        return keys if isinstance(keys, list) else []

    def get_api_keys_health(self) -> Dict[str, Any]:
        """Возвращает health по API ключам."""
        payload = self._get("/api/v1/keys/health", cli_command="keys.health")
        return payload if isinstance(payload, dict) else {}

    def run_api_keys_health_check(self) -> Dict[str, Any]:
        """Запускает online health-check ключей."""
        payload = self._post("/api/v1/keys/health/check", {}, cli_command="keys.health.check")
        return payload if isinstance(payload, dict) else {}

    def validate_api_key(self, key_name: str) -> Dict[str, Any]:
        """Валидирует один API ключ по имени."""
        payload = self._post(
            f"/api/v1/keys/{key_name}/validate",
            {},
            cli_command="keys.validate",
            cli_arguments={"key_name": key_name},
        )
        return payload if isinstance(payload, dict) else {}
