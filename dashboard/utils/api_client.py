"""
VagusAPIClient — HTTP-клиент для взаимодействия Dashboard с Vagus API.

Хранит JWT-токен в st.session_state и прокидывает его в каждый запрос.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
import streamlit as st

_TIMEOUT = 30.0


class VagusAPIClient:
    """Синхронный HTTP-клиент для Vagus API, интегрированный со Streamlit."""

    def __init__(self, api_url: str | None = None):
        url = api_url or st.session_state.get("api_url", "http://localhost:8000")
        self.api_url: str = url.rstrip("/")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        token: str | None = st.session_state.get("jwt_token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: Dict[str, Any] | None = None,
        data: Dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Low-level request wrapper with unified error handling."""
        with httpx.Client(
            base_url=self.api_url,
            headers=self._headers(),
            timeout=_TIMEOUT,
        ) as client:
            response = client.request(
                method, path, json=json, params=params, data=data,
            )
            response.raise_for_status()
            return response

    # ------------------------------------------------------------------
    # auth
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> bool:
        """
        POST /auth/token — получает JWT и сохраняет в session_state.

        Returns:
            True при успешной аутентификации.
        """
        try:
            with httpx.Client(
                base_url=self.api_url, timeout=_TIMEOUT,
            ) as client:
                resp = client.post(
                    "/auth/token",
                    data={"username": username, "password": password},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
            body = resp.json()
            token = body.get("access_token") or body.get("token")
            if not token:
                return False
            st.session_state["jwt_token"] = token
            st.session_state["username"] = username
            st.session_state["authenticated"] = True
            return True
        except httpx.HTTPStatusError:
            return False
        except httpx.ConnectError:
            return False

    def logout(self) -> None:
        for key in ("jwt_token", "username", "authenticated"):
            st.session_state.pop(key, None)

    # ------------------------------------------------------------------
    # tasks
    # ------------------------------------------------------------------

    def create_task(self, prompt: str, task_type: str = "default") -> Dict[str, Any]:
        """POST /api/v1/tasks — создаёт задачу."""
        payload = {
            "prompt": prompt,
            "task_type": task_type,
            "user_id": st.session_state.get("username", "dashboard"),
            "chat_id": "dashboard",
        }
        resp = self._request("POST", "/api/v1/tasks", json=payload)
        return resp.json()

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """GET /api/v1/tasks/{task_id} — статус задачи."""
        resp = self._request("GET", f"/api/v1/tasks/{task_id}")
        return resp.json()

    # ------------------------------------------------------------------
    # monitoring
    # ------------------------------------------------------------------

    def get_system_status(self) -> Dict[str, Any]:
        """GET /api/v1/system/status — метрики системы."""
        resp = self._request("GET", "/api/v1/system/status")
        return resp.json()

    # ------------------------------------------------------------------
    # agents
    # ------------------------------------------------------------------

    def get_agents(self) -> List[Dict[str, Any]]:
        """GET /api/v1/agents — список агентов."""
        resp = self._request("GET", "/api/v1/agents")
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("agents", [])

    def toggle_agent(self, agent_id: str, enabled: bool) -> Dict[str, Any]:
        """PATCH /api/v1/agents/{agent_id} — вкл/выкл агента."""
        resp = self._request(
            "PATCH",
            f"/api/v1/agents/{agent_id}",
            json={"enabled": enabled},
        )
        return resp.json()

    # ------------------------------------------------------------------
    # settings
    # ------------------------------------------------------------------

    def get_config(self) -> Dict[str, Any]:
        """GET /api/v1/config — текущая конфигурация."""
        resp = self._request("GET", "/api/v1/config")
        return resp.json()

    def update_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """PUT /api/v1/config — обновление конфигурации."""
        resp = self._request("PUT", "/api/v1/config", json=config)
        return resp.json()

    def get_users(self) -> List[Dict[str, Any]]:
        """GET /api/v1/users — список пользователей."""
        resp = self._request("GET", "/api/v1/users")
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("users", [])
