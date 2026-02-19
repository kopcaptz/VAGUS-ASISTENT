"""Health and security monitoring for runtime plugins."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from ..core.models import PluginLifecycleState, PluginPermissions
from ..registry import PluginRegistry


class PluginHealthStatus(str, Enum):
    """High-level health status for plugin runtime."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"


@dataclass
class PluginRuntimeMetrics:
    """Accumulated plugin runtime metrics."""

    executions: int = 0
    errors: int = 0
    total_execution_time_seconds: float = 0.0
    max_memory_usage_mb: float = 0.0
    security_violations: int = 0
    last_error_message: Optional[str] = None

    @property
    def average_execution_time_seconds(self) -> float:
        if self.executions == 0:
            return 0.0
        return self.total_execution_time_seconds / self.executions

    @property
    def error_rate(self) -> float:
        if self.executions == 0:
            return 0.0
        return self.errors / self.executions


class PluginMonitor:
    """Monitor plugin health and disable suspicious plugins automatically."""

    def __init__(
        self,
        registry: Optional[PluginRegistry] = None,
        *,
        max_error_rate: float = 0.5,
        security_violation_threshold: int = 3,
        alert_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.registry = registry or PluginRegistry()
        self.max_error_rate = max_error_rate
        self.security_violation_threshold = security_violation_threshold
        self.alert_callback = alert_callback
        self._metrics: dict[str, PluginRuntimeMetrics] = {}
        self._alerts: list[str] = []

    def record_execution(
        self,
        plugin_name: str,
        *,
        execution_time_seconds: float,
        memory_usage_mb: float,
        failed: bool = False,
        error_message: Optional[str] = None,
    ) -> None:
        metrics = self._metrics.setdefault(plugin_name, PluginRuntimeMetrics())
        metrics.executions += 1
        metrics.total_execution_time_seconds += max(0.0, execution_time_seconds)
        metrics.max_memory_usage_mb = max(metrics.max_memory_usage_mb, max(0.0, memory_usage_mb))
        if failed:
            metrics.errors += 1
            metrics.last_error_message = error_message or "Plugin execution failed"

    def record_security_violation(self, plugin_name: str, details: str) -> None:
        metrics = self._metrics.setdefault(plugin_name, PluginRuntimeMetrics())
        metrics.security_violations += 1
        metrics.last_error_message = details
        self._emit_alert(
            f"Security violation in plugin '{plugin_name}': {details}. "
            f"count={metrics.security_violations}"
        )
        if metrics.security_violations >= self.security_violation_threshold:
            self._disable_plugin(
                plugin_name,
                f"Security violations exceeded threshold ({metrics.security_violations})",
            )

    def evaluate_plugin(
        self,
        plugin_name: str,
        permissions: Optional[PluginPermissions] = None,
    ) -> PluginHealthStatus:
        metrics = self._metrics.setdefault(plugin_name, PluginRuntimeMetrics())
        status = PluginHealthStatus.HEALTHY

        if permissions is not None:
            if metrics.max_memory_usage_mb > permissions.max_memory_mb:
                self._disable_plugin(
                    plugin_name,
                    (
                        f"Memory usage limit exceeded: observed {metrics.max_memory_usage_mb:.2f} MB "
                        f"> allowed {permissions.max_memory_mb} MB"
                    ),
                )
                return PluginHealthStatus.DISABLED

            if metrics.average_execution_time_seconds > permissions.max_execution_time_seconds:
                self._disable_plugin(
                    plugin_name,
                    (
                        f"Execution time limit exceeded: avg {metrics.average_execution_time_seconds:.2f}s "
                        f"> allowed {permissions.max_execution_time_seconds}s"
                    ),
                )
                return PluginHealthStatus.DISABLED

        if metrics.executions >= 3 and metrics.error_rate > self.max_error_rate:
            self._disable_plugin(
                plugin_name,
                f"Error rate {metrics.error_rate:.2f} exceeded threshold {self.max_error_rate:.2f}",
            )
            return PluginHealthStatus.DISABLED

        if metrics.executions >= 3 and metrics.error_rate > self.max_error_rate / 2:
            status = PluginHealthStatus.DEGRADED
            self._emit_alert(
                f"Plugin '{plugin_name}' is degraded. Error rate={metrics.error_rate:.2f}"
            )

        plugin = self.registry.get_plugin(plugin_name)
        if plugin and plugin.state.state == PluginLifecycleState.DISABLED:
            return PluginHealthStatus.DISABLED

        return status

    def get_metrics(self, plugin_name: str) -> PluginRuntimeMetrics:
        return self._metrics.setdefault(plugin_name, PluginRuntimeMetrics())

    def get_alerts(self) -> list[str]:
        return list(self._alerts)

    def clear(self) -> None:
        self._metrics.clear()
        self._alerts.clear()

    def _disable_plugin(self, plugin_name: str, reason: str) -> None:
        plugin = self.registry.get_plugin(plugin_name)
        if plugin is not None:
            plugin.state.state = PluginLifecycleState.DISABLED
            plugin.state.error_message = reason
        self._emit_alert(f"Plugin '{plugin_name}' disabled: {reason}")

    def _emit_alert(self, message: str) -> None:
        self._alerts.append(message)
        if self.alert_callback:
            self.alert_callback(message)
