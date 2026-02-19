"""Plugin usage analytics and recommendation engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class PluginUsageMetrics:
    """Aggregated runtime metrics for a plugin."""

    calls: int = 0
    successes: int = 0
    failures: int = 0
    total_execution_time_seconds: float = 0.0
    last_used: Optional[datetime] = None

    @property
    def average_execution_time_seconds(self) -> float:
        if self.calls == 0:
            return 0.0
        return self.total_execution_time_seconds / self.calls

    @property
    def success_rate(self) -> float:
        if self.calls == 0:
            return 0.0
        return self.successes / self.calls


class PluginAnalytics:
    """Collects plugin usage metrics and provides insights."""

    def __init__(self) -> None:
        self._metrics: dict[str, PluginUsageMetrics] = {}
        self._plugin_categories: dict[str, str] = {}

    def set_plugin_category(self, plugin_name: str, category: str) -> None:
        self._plugin_categories[plugin_name] = category

    def record_call(
        self,
        plugin_name: str,
        *,
        execution_time_seconds: float,
        success: bool,
    ) -> None:
        metrics = self._metrics.setdefault(plugin_name, PluginUsageMetrics())
        metrics.calls += 1
        metrics.total_execution_time_seconds += max(0.0, float(execution_time_seconds))
        metrics.last_used = datetime.now(timezone.utc)
        if success:
            metrics.successes += 1
        else:
            metrics.failures += 1

    def get_metrics(self, plugin_name: str) -> PluginUsageMetrics:
        return self._metrics.setdefault(plugin_name, PluginUsageMetrics())

    def get_popularity(self, limit: int = 10) -> list[dict[str, Any]]:
        ranking = sorted(
            (
                {
                    "plugin_name": name,
                    "calls": data.calls,
                    "success_rate": data.success_rate,
                    "average_execution_time_seconds": data.average_execution_time_seconds,
                    "category": self._plugin_categories.get(name, "uncategorized"),
                }
                for name, data in self._metrics.items()
            ),
            key=lambda item: (item["calls"], item["success_rate"]),
            reverse=True,
        )
        return ranking[: max(1, limit)]

    def get_dashboard_data(self) -> dict[str, Any]:
        total_calls = sum(item.calls for item in self._metrics.values())
        total_failures = sum(item.failures for item in self._metrics.values())
        success_rate = 0.0 if total_calls == 0 else (total_calls - total_failures) / total_calls

        return {
            "summary": {
                "total_plugins": len(self._metrics),
                "total_calls": total_calls,
                "success_rate": success_rate,
            },
            "plugins": self.get_popularity(limit=max(1, len(self._metrics))),
        }

    def recommend_plugins(
        self,
        *,
        installed_plugins: list[str],
        marketplace_plugins: list[dict[str, Any]],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        installed = set(installed_plugins)
        top_categories = self._top_categories(limit=3)

        recommendations: list[dict[str, Any]] = []
        for plugin in marketplace_plugins:
            plugin_id = str(plugin.get("plugin_id") or plugin.get("name") or "").strip()
            if not plugin_id or plugin_id in installed:
                continue

            category = str(plugin.get("category", "uncategorized"))
            score = float(plugin.get("avg_rating", 0.0)) + float(plugin.get("review_count", 0)) * 0.05
            if category in top_categories:
                score += 2.0

            recommendations.append(
                {
                    "plugin_id": plugin_id,
                    "category": category,
                    "score": score,
                }
            )

        recommendations.sort(key=lambda item: item["score"], reverse=True)
        return recommendations[: max(1, limit)]

    def _top_categories(self, limit: int = 3) -> list[str]:
        weights: dict[str, int] = {}
        for plugin_name, metrics in self._metrics.items():
            category = self._plugin_categories.get(plugin_name, "uncategorized")
            weights[category] = weights.get(category, 0) + metrics.calls
        ranked = sorted(weights.items(), key=lambda item: item[1], reverse=True)
        return [item[0] for item in ranked[:limit]]
