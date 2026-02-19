"""
HTTP client for the Streamlit Dashboard.
All communication with Vagus goes through the REST API.
"""

from typing import Any, Dict, List, Optional

import httpx
import streamlit as st

API_BASE_URL = "http://localhost:8000/api/v1"


class VagusAPIClient:
    """Synchronous HTTP client for Streamlit pages."""

    def __init__(self):
        self._token: Optional[str] = st.session_state.get("access_token")

    @property
    def _headers(self) -> Dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    def login(self, username: str, password: str) -> bool:
        """Authenticates and stores the JWT token in session_state."""
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{API_BASE_URL}/auth/token",
                data={"username": username, "password": password},
            )
        if resp.status_code == 200:
            data = resp.json()
            st.session_state["access_token"] = data["access_token"]
            st.session_state["refresh_token"] = data.get("refresh_token", "")
            self._token = data["access_token"]
            return True
        return False

    def create_task(self, prompt: str, task_type: str = "default") -> Dict[str, Any]:
        """Creates a new task."""
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{API_BASE_URL}/tasks",
                json={"prompt": prompt, "task_type": task_type},
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Gets task status."""
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{API_BASE_URL}/tasks/{task_id}",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def list_tasks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Lists recent tasks."""
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{API_BASE_URL}/tasks",
                params={"limit": limit},
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json().get("tasks", [])

    def get_system_status(self) -> Dict[str, Any]:
        """Gets system status and metrics."""
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{API_BASE_URL}/status",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_agents(self) -> List[Dict[str, Any]]:
        """Lists registered agents."""
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{API_BASE_URL}/agents",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()
