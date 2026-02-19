"""Production security hardening for plugin runtime operations."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


class PluginSecurityHardeningError(PermissionError):
    """Raised when plugin operation violates hardening policy."""


@dataclass
class PluginResourceQuota:
    """Resource quotas for plugin runtime operations."""

    max_calls_per_minute: int = 60
    max_memory_mb: float = 512.0
    max_execution_time_seconds: float = 30.0


@dataclass
class PluginSecurityAuditRecord:
    timestamp: datetime
    plugin_name: str
    operation: str
    allowed: bool
    reason: str


class PluginSecurityHardening:
    """Enforces rate limiting, quotas, signatures and audit logging."""

    def __init__(
        self,
        *,
        production_mode: bool = False,
        require_signatures: bool = True,
    ) -> None:
        self.production_mode = production_mode
        self.require_signatures = require_signatures
        self._quotas: dict[str, PluginResourceQuota] = {}
        self._rate_counters: dict[str, deque[float]] = {}
        self._audit: list[PluginSecurityAuditRecord] = []

    def register_quota(self, plugin_name: str, quota: PluginResourceQuota) -> None:
        self._quotas[plugin_name] = quota

    def check_operation(
        self,
        plugin_name: str,
        *,
        operation: str,
        signed: bool = False,
        estimated_memory_mb: float = 0.0,
        estimated_execution_time_seconds: float = 0.0,
    ) -> None:
        quota = self._quotas.get(plugin_name, PluginResourceQuota())

        if self.production_mode and self.require_signatures and not signed:
            self._audit_record(plugin_name, operation, False, "Digital signature required in production")
            raise PluginSecurityHardeningError("Digital signatures are required in production")

        self._check_rate_limit(plugin_name, quota.max_calls_per_minute, operation)
        self._check_memory(plugin_name, estimated_memory_mb, quota.max_memory_mb, operation)
        self._check_execution_time(
            plugin_name,
            estimated_execution_time_seconds,
            quota.max_execution_time_seconds,
            operation,
        )
        self._audit_record(plugin_name, operation, True, "Operation allowed")

    def get_audit_log(self, plugin_name: Optional[str] = None) -> list[PluginSecurityAuditRecord]:
        if plugin_name is None:
            return list(self._audit)
        return [record for record in self._audit if record.plugin_name == plugin_name]

    def clear_audit_log(self) -> None:
        self._audit.clear()

    def _check_rate_limit(self, plugin_name: str, max_calls_per_minute: int, operation: str) -> None:
        now = time.time()
        window_start = now - 60.0
        counter = self._rate_counters.setdefault(plugin_name, deque())
        while counter and counter[0] < window_start:
            counter.popleft()
        if len(counter) >= max(1, int(max_calls_per_minute)):
            self._audit_record(
                plugin_name,
                operation,
                False,
                f"Rate limit exceeded: {len(counter)} calls/minute",
            )
            raise PluginSecurityHardeningError("Plugin rate limit exceeded")
        counter.append(now)

    def _check_memory(self, plugin_name: str, usage_mb: float, max_memory_mb: float, operation: str) -> None:
        if usage_mb <= 0:
            return
        if usage_mb > max_memory_mb:
            self._audit_record(
                plugin_name,
                operation,
                False,
                f"Memory quota exceeded: {usage_mb:.2f} MB > {max_memory_mb:.2f} MB",
            )
            raise PluginSecurityHardeningError("Plugin memory quota exceeded")

    def _check_execution_time(
        self,
        plugin_name: str,
        execution_seconds: float,
        max_execution_seconds: float,
        operation: str,
    ) -> None:
        if execution_seconds <= 0:
            return
        if execution_seconds > max_execution_seconds:
            self._audit_record(
                plugin_name,
                operation,
                False,
                (
                    "Execution time quota exceeded: "
                    f"{execution_seconds:.2f}s > {max_execution_seconds:.2f}s"
                ),
            )
            raise PluginSecurityHardeningError("Plugin execution time quota exceeded")

    def _audit_record(self, plugin_name: str, operation: str, allowed: bool, reason: str) -> None:
        self._audit.append(
            PluginSecurityAuditRecord(
                timestamp=datetime.now(timezone.utc),
                plugin_name=plugin_name,
                operation=operation,
                allowed=allowed,
                reason=reason,
            )
        )
