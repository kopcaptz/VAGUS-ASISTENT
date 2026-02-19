"""
Вспомогательные функции для визуализации данных.
"""

from typing import Any, Dict, List


def format_uptime(seconds: float) -> str:
    """Форматирует uptime в читаемый вид."""
    if seconds < 60:
        return f"{seconds:.0f} сек"
    elif seconds < 3600:
        return f"{seconds / 60:.1f} мин"
    elif seconds < 86400:
        return f"{seconds / 3600:.1f} ч"
    return f"{seconds / 86400:.1f} дн"


def format_cost(cost: float) -> str:
    """Форматирует стоимость."""
    return f"${cost:.4f}"


def extract_metrics(status: Dict[str, Any]) -> Dict[str, Any]:
    """Извлекает ключевые метрики из статуса системы."""
    l1 = status.get("layer1_stats", {})
    return {
        "agents": status.get("layer2_agents_count", 0),
        "active_tasks": status.get("active_tasks_count", 0),
        "uptime": format_uptime(status.get("uptime_seconds", 0)),
        "requests": l1.get("requests", 0),
        "total_cost": format_cost(l1.get("total_cost", 0)),
        "cache_hit_rate": l1.get("cache", {}).get("hit_rate_percent", 0),
    }
