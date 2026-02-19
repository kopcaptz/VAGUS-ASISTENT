"""
Error classification and analytics storage.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


TRANSIENT_KEYWORDS = (
    "timeout",
    "timed out",
    "rate limit",
    "rate_limit",
    "temporarily unavailable",
)
PERMANENT_KEYWORDS = (
    "validation",
    "invalid",
    "auth",
    "unauthorized",
    "forbidden",
    "permission",
    "schema",
)
INFRASTRUCTURE_KEYWORDS = (
    "database",
    "sqlite",
    "redis",
    "network",
    "dns",
    "connection",
)


def classify_error(
    error_message: str,
    *,
    error_type: Optional[str] = None,
) -> str:
    """
    Classifies error into:
      - transient
      - permanent
      - infrastructure
    """
    merged = f"{error_type or ''} {error_message or ''}".lower()
    if any(k in merged for k in INFRASTRUCTURE_KEYWORDS):
        return "infrastructure"
    if any(k in merged for k in TRANSIENT_KEYWORDS):
        return "transient"
    if any(k in merged for k in PERMANENT_KEYWORDS):
        return "permanent"
    return "permanent"


@dataclass(slots=True)
class ErrorEvent:
    id: int
    timestamp: str
    source: str
    error_type: str
    classification: str
    message: str
    metadata: dict[str, Any]


class ErrorAnalyticsStorage:
    """SQLite-backed error analytics with basic aggregation."""

    def __init__(self, db_path: str = "error_analytics.db"):
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
                CREATE TABLE IF NOT EXISTS error_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metadata TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_error_events_timestamp
                ON error_events(timestamp)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_error_events_classification
                ON error_events(classification)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_error_events_source
                ON error_events(source)
                """
            )

    def record_error(
        self,
        *,
        source: str,
        message: str,
        error_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> dict[str, Any]:
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        resolved_error_type = error_type or "unknown_error"
        classification = classify_error(message, error_type=resolved_error_type)
        metadata_json = json.dumps(metadata or {}, ensure_ascii=False, default=str)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO error_events
                (
                    timestamp, source, error_type, classification, message, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    source or "unknown",
                    resolved_error_type,
                    classification,
                    message or "",
                    metadata_json,
                ),
            )

        return {
            "timestamp": ts,
            "source": source or "unknown",
            "error_type": resolved_error_type,
            "classification": classification,
            "message": message or "",
            "metadata": metadata or {},
        }

    def _decode_metadata(self, payload: str) -> dict[str, Any]:
        try:
            parsed = json.loads(payload)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    def list_events(
        self,
        *,
        limit: int = 200,
        classification: Optional[str] = None,
        source: Optional[str] = None,
        since_timestamp: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if classification:
            conditions.append("classification = ?")
            params.append(classification)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if since_timestamp:
            conditions.append("timestamp >= ?")
            params.append(since_timestamp)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT id, timestamp, source, error_type, classification, message, metadata
            FROM error_events
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
            item["metadata"] = self._decode_metadata(item.get("metadata", "{}"))
            result.append(item)
        return result

    def _window_since(self, window_minutes: int) -> str:
        since = datetime.now(timezone.utc) - timedelta(minutes=max(1, int(window_minutes)))
        return since.isoformat()

    def get_error_rate_by_type(self, *, window_minutes: int = 60) -> dict[str, Any]:
        since_ts = self._window_since(window_minutes)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT classification, COUNT(*) AS c
                FROM error_events
                WHERE timestamp >= ?
                GROUP BY classification
                """,
                (since_ts,),
            ).fetchall()
        counts = {"transient": 0, "permanent": 0, "infrastructure": 0}
        total = 0
        for row in rows:
            cls = str(row["classification"])
            cnt = int(row["c"])
            counts[cls] = cnt
            total += cnt

        rates = {
            key: (float(value) / float(total) * 100.0 if total > 0 else 0.0)
            for key, value in counts.items()
        }
        return {
            "window_minutes": window_minutes,
            "total_errors": total,
            "counts": counts,
            "rates_percent": rates,
        }

    def get_top_error_sources(
        self,
        *,
        limit: int = 5,
        window_minutes: int = 60,
    ) -> list[dict[str, Any]]:
        since_ts = self._window_since(window_minutes)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT source, COUNT(*) AS c
                FROM error_events
                WHERE timestamp >= ?
                GROUP BY source
                ORDER BY c DESC, source ASC
                LIMIT ?
                """,
                (since_ts, max(1, int(limit))),
            ).fetchall()
        return [{"source": str(row["source"]), "count": int(row["c"])} for row in rows]

    def get_correlation_snapshot(
        self,
        *,
        metrics_context: Optional[dict[str, Any]] = None,
        window_minutes: int = 60,
    ) -> dict[str, Any]:
        rates = self.get_error_rate_by_type(window_minutes=window_minutes)
        total_errors = int(rates["total_errors"])
        counts = rates["counts"]
        requests = 0.0
        cache_hit_rate = 0.0
        if isinstance(metrics_context, dict):
            requests = float(metrics_context.get("requests", 0.0) or 0.0)
            cache_hit_rate = float(metrics_context.get("cache_hit_rate_percent", 0.0) or 0.0)
        error_to_request_ratio = (
            float(total_errors) / requests if requests > 0 else float(total_errors)
        )
        infra_share = float(counts.get("infrastructure", 0)) / float(total_errors or 1)
        transient_share = float(counts.get("transient", 0)) / float(total_errors or 1)

        return {
            "window_minutes": window_minutes,
            "error_to_request_ratio": error_to_request_ratio,
            "cache_hit_rate_percent": cache_hit_rate,
            "infrastructure_share": infra_share,
            "transient_share": transient_share,
        }

    def build_analytics_snapshot(
        self,
        *,
        window_minutes: int = 60,
        top_sources_limit: int = 5,
        metrics_context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        return {
            "error_rate_by_type": self.get_error_rate_by_type(window_minutes=window_minutes),
            "top_error_sources": self.get_top_error_sources(
                limit=top_sources_limit,
                window_minutes=window_minutes,
            ),
            "correlation": self.get_correlation_snapshot(
                metrics_context=metrics_context,
                window_minutes=window_minutes,
            ),
            "recent_events": self.list_events(
                limit=50,
                since_timestamp=self._window_since(window_minutes),
            ),
        }


__all__ = [
    "TRANSIENT_KEYWORDS",
    "PERMANENT_KEYWORDS",
    "INFRASTRUCTURE_KEYWORDS",
    "ErrorAnalyticsStorage",
    "ErrorEvent",
    "classify_error",
]
