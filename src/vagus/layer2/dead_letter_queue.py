"""
Dead Letter Queue storage for failed tasks.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass(slots=True)
class DeadLetterQueueEntry:
    id: int
    task_id: str
    agent_type: str
    error_message: str
    stack_trace: str
    timestamp: str
    retry_count: int
    status: str
    manual_fix_note: Optional[str]
    task_payload: Optional[dict[str, Any]]


class DeadLetterQueueStorage:
    """SQLite-backed Dead Letter Queue."""

    def __init__(self, db_path: str = "dead_letter_queue.db"):
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
                CREATE TABLE IF NOT EXISTS dead_letter_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    agent_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    stack_trace TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    manual_fix_note TEXT,
                    task_payload TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dlq_timestamp
                ON dead_letter_queue(timestamp)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dlq_task_id
                ON dead_letter_queue(task_id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dlq_status
                ON dead_letter_queue(status)
                """
            )

    def add_failed_task(
        self,
        *,
        task_id: str,
        agent_type: str,
        error_message: str,
        stack_trace: str,
        retry_count: int = 0,
        status: str = "pending",
        task_payload: Optional[dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        payload_json = (
            json.dumps(task_payload, ensure_ascii=False, default=str)
            if task_payload is not None
            else None
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO dead_letter_queue
                (
                    task_id, agent_type, error_message, stack_trace,
                    timestamp, retry_count, status, manual_fix_note, task_payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    agent_type,
                    error_message,
                    stack_trace,
                    ts,
                    int(retry_count),
                    status,
                    None,
                    payload_json,
                ),
            )

    def _decode_payload(self, raw_payload: Optional[str]) -> Optional[dict[str, Any]]:
        if not raw_payload:
            return None
        try:
            parsed = json.loads(raw_payload)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    def list_entries(
        self,
        *,
        limit: int = 100,
        status: Optional[str] = None,
        agent_type: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if agent_type:
            conditions.append("agent_type = ?")
            params.append(agent_type)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT
                id, task_id, agent_type, error_message, stack_trace,
                timestamp, retry_count, status, manual_fix_note, task_payload
            FROM dead_letter_queue
            {where_clause}
            ORDER BY id DESC
            LIMIT ?
        """
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["task_payload"] = self._decode_payload(item.get("task_payload"))
            result.append(item)
        return result

    def get_latest_entry(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    id, task_id, agent_type, error_message, stack_trace,
                    timestamp, retry_count, status, manual_fix_note, task_payload
                FROM dead_letter_queue
                WHERE task_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["task_payload"] = self._decode_payload(payload.get("task_payload"))
        return payload

    def update_status(
        self,
        *,
        task_id: str,
        status: str,
        retry_count: Optional[int] = None,
        manual_fix_note: Optional[str] = None,
    ) -> bool:
        entry = self.get_latest_entry(task_id)
        if entry is None:
            return False
        next_retry_count = (
            int(retry_count) if retry_count is not None else int(entry.get("retry_count", 0))
        )
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE dead_letter_queue
                SET status = ?, retry_count = ?, manual_fix_note = ?
                WHERE id = ?
                """,
                (status, next_retry_count, manual_fix_note, entry["id"]),
            )
        return True

    def mark_manual_fix(self, *, task_id: str, note: str) -> bool:
        return self.update_status(
            task_id=task_id,
            status="manually_fixed",
            manual_fix_note=note,
        )

    def mark_retry_requested(self, *, task_id: str, retry_count: int) -> bool:
        return self.update_status(
            task_id=task_id,
            status="retry_requested",
            retry_count=retry_count,
        )
