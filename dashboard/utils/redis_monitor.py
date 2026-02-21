"""
Утилиты для сбора метрик Redis Streams.
Вызывает API /monitoring/redis и возвращает структурированные данные.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Type alias for client - avoids circular import
Client = Any


def fetch_redis_metrics(client: Client) -> Dict[str, Any]:
    """
    Загружает метрики Redis Streams через API.
    Returns: {"available": bool, "stream_name": str, "consumer_groups": [...], "dlq_count": int, "error": str?}
    """
    try:
        return client.get_monitoring_redis()
    except Exception as exc:
        return {"available": False, "error": str(exc), "consumer_groups": [], "dlq_count": 0}
