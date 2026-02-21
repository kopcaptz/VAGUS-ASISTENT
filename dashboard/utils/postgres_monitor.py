"""
Утилиты для сбора метрик PostgreSQL/SQLite.
Вызывает API /monitoring/postgres и возвращает структурированные данные.
"""

from __future__ import annotations

from typing import Any, Dict

Client = Any


def fetch_postgres_metrics(client: Client) -> Dict[str, Any]:
    """
    Загружает метрики БД через API.
    Returns: {"available": bool, "backend": str, "artifacts_count": int, "relationships_count": int, ...}
    """
    try:
        return client.get_monitoring_postgres()
    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
            "artifacts_count": 0,
            "relationships_count": 0,
            "query_time_ms": None,
        }
