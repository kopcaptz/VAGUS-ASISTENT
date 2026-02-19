"""
SQLite-backed audit trail for API, CLI and WebSocket activities.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass(slots=True)
class AuditLogEntry:
    id: int
    timestamp: str
    user_id: Optional[str]
    action: str
    resource: str
    details: str
    ip_address: Optional[str]


class AuditTrail:
    """Main audit storage facade."""

    def __init__(self, db_path: str = "audit_trail.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user_id TEXT,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    details TEXT NOT NULL,
                    ip_address TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp
                ON audit_log(timestamp)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_log_user
                ON audit_log(user_id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_log_action
                ON audit_log(action)
                """
            )

    def log_action(
        self,
        *,
        user_id: Optional[str],
        action: str,
        resource: str,
        details: Any,
        ip_address: Optional[str],
        timestamp: Optional[str] = None,
    ) -> None:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        if isinstance(details, str):
            details_json = details
        else:
            details_json = json.dumps(details, ensure_ascii=False, default=str)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (timestamp, user_id, action, resource, details, ip_address)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ts, user_id, action, resource, details_json, ip_address),
            )

    def list_logs(
        self,
        *,
        limit: int = 100,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        conditions = []
        params: list[Any] = []
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if action:
            conditions.append("action = ?")
            params.append(action)
        if resource:
            conditions.append("resource = ?")
            params.append(resource)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT id, timestamp, user_id, action, resource, details, ip_address
            FROM audit_log
            {where}
            ORDER BY id DESC
            LIMIT ?
        """
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
