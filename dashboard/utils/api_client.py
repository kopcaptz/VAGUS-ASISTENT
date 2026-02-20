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

    def __init__(
        self,
        base_url: str = API_BASE_URL,
        token: Optional[str] = None,
        *,
        transport: Any | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._transport = transport

    @property
    def root_url(self) -> str:
        if self.base_url.endswith("/api/v1"):
            return self.base_url[: -len("/api/v1")]
        return self.base_url

    @property
    def websocket_root_url(self) -> str:
        root = self.root_url
        if root.startswith("https://"):
            return "wss://" + root[len("https://") :]
        if root.startswith("http://"):
            return "ws://" + root[len("http://") :]
        return root

    @property
    def _headers(self) -> Dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    def _client(self, timeout: int):
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        kwargs: Dict[str, Any] = {"timeout": timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.Client(**kwargs)

    def login(self, username: str, password: str) -> bool:
        """Аутентификация — сохраняет токен."""
        if not HTTPX_AVAILABLE:
            return False
        try:
            with self._client(timeout=10) as client:
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
        with self._client(timeout=30) as client:
            resp = client.post(
                f"{self.base_url}/tasks",
                json={"prompt": prompt, "task_type": task_type},
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Статус задачи."""
        with self._client(timeout=10) as client:
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
        with self._client(timeout=10) as client:
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
        with self._client(timeout=10) as client:
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
        with self._client(timeout=10) as client:
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
        with self._client(timeout=10) as client:
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
        with self._client(timeout=10) as client:
            resp = client.get(
                f"{self.root_url}/health/detailed",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_dead_letter_queue(
        self,
        *,
        limit: int = 100,
        status: Optional[str] = None,
        agent_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not HTTPX_AVAILABLE:
            return []
        params = [f"limit={int(limit)}"]
        if status:
            params.append(f"status={status}")
        if agent_type:
            params.append(f"agent_type={agent_type}")
        query = "&".join(params)
        with self._client(timeout=10) as client:
            resp = client.get(
                f"{self.base_url}/admin/dead-letter-queue?{query}",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def retry_dead_letter_task(
        self,
        task_id: str,
        *,
        prompt: Optional[str] = None,
        task_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        payload: Dict[str, Any] = {}
        if prompt is not None:
            payload["prompt"] = prompt
        if task_type is not None:
            payload["task_type"] = task_type
        if metadata is not None:
            payload["metadata"] = metadata
        with self._client(timeout=60) as client:
            resp = client.post(
                f"{self.base_url}/admin/dead-letter-queue/{task_id}/retry",
                json=payload,
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def mark_dead_letter_manual_fix(self, task_id: str, note: str) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        with self._client(timeout=20) as client:
            resp = client.post(
                f"{self.base_url}/admin/dead-letter-queue/{task_id}/manual-fix",
                json={"note": note},
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_circuit_breakers(self) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return {}
        with self._client(timeout=10) as client:
            resp = client.get(
                f"{self.base_url}/admin/circuit-breakers",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def reset_circuit_breaker(self, provider_id: str) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        with self._client(timeout=10) as client:
            resp = client.post(
                f"{self.base_url}/admin/circuit-breakers/{provider_id}/reset",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_error_analytics(
        self,
        *,
        window_minutes: int = 60,
        top_sources_limit: int = 10,
    ) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return {}
        with self._client(timeout=20) as client:
            resp = client.get(
                f"{self.base_url}/admin/error-analytics"
                f"?window_minutes={int(window_minutes)}&top_sources_limit={int(top_sources_limit)}",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def list_api_keys(self) -> List[Dict[str, Any]]:
        if not HTTPX_AVAILABLE:
            return []
        with self._client(timeout=15) as client:
            resp = client.get(f"{self.base_url}/keys", headers=self._headers)
        resp.raise_for_status()
        payload = resp.json()
        keys = payload.get("keys", []) if isinstance(payload, dict) else []
        return keys if isinstance(keys, list) else []

    def create_api_key(
        self,
        *,
        name: str,
        key_type: str,
        value: str,
        expires_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        payload: Dict[str, Any] = {"name": name, "type": key_type, "value": value}
        if expires_at:
            payload["expires_at"] = expires_at
        with self._client(timeout=20) as client:
            resp = client.post(f"{self.base_url}/keys", json=payload, headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def update_api_key(
        self,
        key_name: str,
        *,
        value: Optional[str] = None,
        expires_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        payload: Dict[str, Any] = {}
        if value is not None:
            payload["value"] = value
        if expires_at is not None:
            payload["expires_at"] = expires_at
        with self._client(timeout=20) as client:
            resp = client.put(f"{self.base_url}/keys/{key_name}", json=payload, headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def delete_api_key(self, key_name: str) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        with self._client(timeout=20) as client:
            resp = client.delete(f"{self.base_url}/keys/{key_name}", headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def validate_api_key(self, key_name: str) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        with self._client(timeout=20) as client:
            resp = client.post(f"{self.base_url}/keys/{key_name}/validate", headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def get_api_keys_health(self) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return {}
        with self._client(timeout=20) as client:
            resp = client.get(f"{self.base_url}/keys/health", headers=self._headers)
        resp.raise_for_status()
        payload = resp.json()
        return payload if isinstance(payload, dict) else {}

    def run_api_keys_health_check(self) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        with self._client(timeout=30) as client:
            resp = client.post(f"{self.base_url}/keys/health/check", headers=self._headers)
        resp.raise_for_status()
        payload = resp.json()
        return payload if isinstance(payload, dict) else {}

    def get_plugins(self) -> List[Dict[str, Any]]:
        if not HTTPX_AVAILABLE:
            return []
        with self._client(timeout=20) as client:
            resp = client.get(f"{self.base_url}/plugins", headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def get_plugin(self, plugin_name: str) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return {}
        with self._client(timeout=20) as client:
            resp = client.get(f"{self.base_url}/plugins/{plugin_name}", headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def install_plugin(self, source: str, version: Optional[str] = None) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        payload: Dict[str, Any] = {"source": source}
        if version:
            payload["version"] = version
        with self._client(timeout=60) as client:
            resp = client.post(f"{self.base_url}/plugins/install", json=payload, headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def enable_plugin(self, plugin_name: str) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        with self._client(timeout=20) as client:
            resp = client.post(f"{self.base_url}/plugins/{plugin_name}/enable", headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def disable_plugin(self, plugin_name: str) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        with self._client(timeout=20) as client:
            resp = client.post(f"{self.base_url}/plugins/{plugin_name}/disable", headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def uninstall_plugin(self, plugin_name: str, *, force: bool = False) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        query = "?force=true" if force else ""
        with self._client(timeout=30) as client:
            resp = client.delete(f"{self.base_url}/plugins/{plugin_name}{query}", headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def get_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return {}
        with self._client(timeout=20) as client:
            resp = client.get(f"{self.base_url}/plugins/{plugin_name}/config", headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    def update_plugin_config(
        self,
        plugin_name: str,
        *,
        settings: Optional[Dict[str, Any]] = None,
        secrets: Optional[Dict[str, Any]] = None,
        ui_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        payload: Dict[str, Any] = {}
        if settings is not None:
            payload["settings"] = settings
        if secrets is not None:
            payload["secrets"] = secrets
        if ui_schema is not None:
            payload["ui_schema"] = ui_schema
        with self._client(timeout=20) as client:
            resp = client.put(
                f"{self.base_url}/plugins/{plugin_name}/config",
                json=payload,
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def marketplace_search_plugins(
        self,
        *,
        query: str = "",
        category: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        if not HTTPX_AVAILABLE:
            return []
        params: Dict[str, Any] = {"q": query, "limit": int(limit)}
        if category:
            params["category"] = category
        with self._client(timeout=20) as client:
            resp = client.get(
                f"{self.base_url}/plugins/marketplace/search",
                params=params,
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def marketplace_categories(self) -> List[str]:
        if not HTTPX_AVAILABLE:
            return []
        with self._client(timeout=20) as client:
            resp = client.get(
                f"{self.base_url}/plugins/marketplace/categories",
                headers=self._headers,
            )
        resp.raise_for_status()
        payload = resp.json()
        return [str(item) for item in payload] if isinstance(payload, list) else []

    def marketplace_plugin_details(self, plugin_id: str) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return {}
        with self._client(timeout=20) as client:
            resp = client.get(
                f"{self.base_url}/plugins/marketplace/{plugin_id}",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def marketplace_install_plugin(
        self,
        plugin_id: str,
        *,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        payload: Dict[str, Any] = {}
        if version:
            payload["version"] = version
        with self._client(timeout=60) as client:
            resp = client.post(
                f"{self.base_url}/plugins/marketplace/{plugin_id}/install",
                json=payload if payload else None,
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def marketplace_trending_plugins(
        self,
        *,
        limit: int = 10,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not HTTPX_AVAILABLE:
            return []
        params: Dict[str, Any] = {"limit": int(limit)}
        if category:
            params["category"] = category
        with self._client(timeout=20) as client:
            resp = client.get(
                f"{self.base_url}/plugins/marketplace/trending",
                params=params,
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_plugin_dependencies(self, plugin_name: str) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return {}
        with self._client(timeout=20) as client:
            resp = client.get(
                f"{self.base_url}/plugins/{plugin_name}/dependencies",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_plugin_statistics(self) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return {}
        with self._client(timeout=20) as client:
            resp = client.get(
                f"{self.base_url}/plugins/statistics",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_plugin_dependency_conflicts(self, plugin_name: str) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return {}
        with self._client(timeout=20) as client:
            resp = client.get(
                f"{self.base_url}/plugins/{plugin_name}/dependencies/conflicts",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def resolve_plugin_dependencies(
        self,
        plugin_name: str,
        *,
        strategy: str = "prefer-installed",
        dry_run: bool = False,
        pin_versions: bool = True,
        export_lock: bool = True,
    ) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        payload = {
            "strategy": strategy,
            "dry_run": dry_run,
            "pin_versions": pin_versions,
            "export_lock": export_lock,
        }
        with self._client(timeout=30) as client:
            resp = client.post(
                f"{self.base_url}/plugins/{plugin_name}/dependencies/resolve",
                json=payload,
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def update_plugin_dependencies(
        self,
        plugin_name: str,
        *,
        updates: Optional[Dict[str, str]] = None,
        pin_versions: bool = False,
        dry_run: bool = False,
        export_lock: bool = True,
        import_lock_content: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        payload: Dict[str, Any] = {
            "updates": updates or {},
            "pin_versions": pin_versions,
            "dry_run": dry_run,
            "export_lock": export_lock,
        }
        if import_lock_content is not None:
            payload["import_lock_content"] = import_lock_content
        with self._client(timeout=30) as client:
            resp = client.post(
                f"{self.base_url}/plugins/{plugin_name}/dependencies/update",
                json=payload,
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def bulk_update_plugin_dependencies(
        self,
        *,
        operations: List[Dict[str, Any]],
        dry_run: bool = False,
        rollback_on_error: bool = True,
        allow_conflicts: bool = False,
        export_lock: bool = True,
    ) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        payload = {
            "operations": operations,
            "dry_run": dry_run,
            "rollback_on_error": rollback_on_error,
            "allow_conflicts": allow_conflicts,
            "export_lock": export_lock,
        }
        with self._client(timeout=45) as client:
            resp = client.post(
                f"{self.base_url}/plugins/dependencies/bulk-update",
                json=payload,
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_hot_reload_status(self) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return {}
        with self._client(timeout=20) as client:
            resp = client.get(
                f"{self.base_url}/plugins/hot-reload/status",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def enable_hot_reload(self) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        with self._client(timeout=20) as client:
            resp = client.post(
                f"{self.base_url}/plugins/hot-reload/enable",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def disable_hot_reload(self) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        with self._client(timeout=20) as client:
            resp = client.post(
                f"{self.base_url}/plugins/hot-reload/disable",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_hot_reload_logs(
        self,
        *,
        limit: int = 100,
        plugin_name: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not HTTPX_AVAILABLE:
            return []
        params: Dict[str, Any] = {"limit": int(limit)}
        if plugin_name:
            params["plugin_name"] = plugin_name
        if event_type:
            params["event_type"] = event_type
        with self._client(timeout=20) as client:
            resp = client.get(
                f"{self.base_url}/plugins/hot-reload/logs",
                params=params,
                headers=self._headers,
            )
        resp.raise_for_status()
        payload = resp.json()
        return payload if isinstance(payload, list) else []

    def get_plugin_reload_history(self, plugin_name: str, *, limit: int = 100) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            return {}
        with self._client(timeout=20) as client:
            resp = client.get(
                f"{self.base_url}/plugins/{plugin_name}/reload-history",
                params={"limit": int(limit)},
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def reload_plugin_now(self, plugin_name: str) -> Dict[str, Any]:
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx not installed")
        with self._client(timeout=30) as client:
            resp = client.post(
                f"{self.base_url}/plugins/{plugin_name}/reload-now",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()
