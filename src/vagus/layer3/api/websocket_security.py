"""
WebSocket hardening utilities: runtime settings and audit storage.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass(slots=True)
class WebSocketRuntimeSettings:
    """Runtime limits and heartbeat settings for WebSocket connections."""

    max_message_size_mb: int = 10
    ping_interval_seconds: int = 30
    ping_timeout_seconds: int = 60
    max_messages_per_minute: int = 100
    status_poll_interval_seconds: float = 0.5

    @property
    def max_message_size_bytes(self) -> int:
        return self.max_message_size_mb * 1024 * 1024


def create_runtime_settings_from_config(config: Optional[object]) -> WebSocketRuntimeSettings:
    """
    Build runtime settings from AppConfig (if available).

    Falls back to secure defaults when config is missing or incomplete.
    """
    defaults = WebSocketRuntimeSettings()
    if config is None:
        return defaults

    websocket_cfg = getattr(config, "websocket", None)
    if websocket_cfg is None:
        return defaults

    return WebSocketRuntimeSettings(
        max_message_size_mb=getattr(websocket_cfg, "max_message_size_mb", defaults.max_message_size_mb),
        ping_interval_seconds=getattr(
            websocket_cfg, "ping_interval_seconds", defaults.ping_interval_seconds
        ),
        ping_timeout_seconds=getattr(websocket_cfg, "ping_timeout_seconds", defaults.ping_timeout_seconds),
        max_messages_per_minute=getattr(
            websocket_cfg, "max_messages_per_minute", defaults.max_messages_per_minute
        ),
        status_poll_interval_seconds=defaults.status_poll_interval_seconds,
    )


class WebSocketAuditStorage:
    """SQLite-backed audit storage for WebSocket lifecycle events."""

    def __init__(self, db_path: str = "websocket_audit.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS websocket_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    user_id TEXT,
                    task_id TEXT,
                    timestamp TEXT NOT NULL,
                    message_size_bytes INTEGER,
                    message_type TEXT,
                    close_code INTEGER,
                    reason TEXT,
                    duration_seconds REAL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_websocket_audit_timestamp
                ON websocket_audit_log(timestamp)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_websocket_audit_task_id
                ON websocket_audit_log(task_id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_websocket_audit_user_id
                ON websocket_audit_log(user_id)
                """
            )

    def log_event(
        self,
        *,
        event_type: str,
        user_id: Optional[str],
        task_id: Optional[str],
        message_size_bytes: Optional[int] = None,
        message_type: Optional[str] = None,
        close_code: Optional[int] = None,
        reason: Optional[str] = None,
        duration_seconds: Optional[float] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO websocket_audit_log
                (
                    event_type, user_id, task_id, timestamp, message_size_bytes,
                    message_type, close_code, reason, duration_seconds
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    user_id,
                    task_id,
                    ts,
                    message_size_bytes,
                    message_type,
                    close_code,
                    reason,
                    duration_seconds,
                ),
            )

    def list_events(
        self,
        *,
        limit: int = 100,
        task_id: Optional[str] = None,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []

        if task_id:
            conditions.append("task_id = ?")
            params.append(task_id)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT
                id, event_type, user_id, task_id, timestamp,
                message_size_bytes, message_type, close_code, reason, duration_seconds
            FROM websocket_audit_log
            {where_clause}
            ORDER BY id DESC
            LIMIT ?
        """
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [dict(row) for row in rows]
