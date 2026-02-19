"""Permission checks and audit logging for plugin sandbox."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Optional

from ..core.models import PermissionLevel, PluginPermissions

PERMISSION_ORDER = {
    PermissionLevel.NONE: 0,
    PermissionLevel.READ: 1,
    PermissionLevel.WRITE: 2,
    PermissionLevel.NETWORK: 3,
    PermissionLevel.SYSTEM: 4,
}


class SecurityViolationError(PermissionError):
    """Raised when plugin attempts forbidden operation."""


@dataclass(frozen=True)
class SecurityAuditEvent:
    """Audit record for security-sensitive plugin operations."""

    timestamp: datetime
    plugin_name: str
    operation: str
    target: str
    allowed: bool
    reason: str


class SecurityManager:
    """Permission manager for plugin sandbox operations."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or logging.getLogger("vagus.plugins.security")
        self._audit_events: list[SecurityAuditEvent] = []
        self._lock = threading.RLock()

    def require_level(
        self,
        plugin_name: str,
        permissions: PluginPermissions,
        required_level: PermissionLevel,
        operation: str,
        target: str = "",
    ) -> None:
        """Ensure plugin has required permission level."""
        granted = self._has_level(permissions.level, required_level)
        reason = (
            f"Permission level '{permissions.level.value}' satisfies '{required_level.value}'"
            if granted
            else f"Permission level '{permissions.level.value}' is below required '{required_level.value}'"
        )
        self._audit(plugin_name, operation, target, granted, reason)
        if not granted:
            raise SecurityViolationError(reason)

    def check_filesystem_access(
        self,
        plugin_name: str,
        permissions: PluginPermissions,
        path: str | Path,
        *,
        write: bool,
    ) -> None:
        """Validate filesystem read/write permission."""
        operation = "filesystem_write" if write else "filesystem_read"
        target = str(path)

        if permissions.level == PermissionLevel.SYSTEM:
            self._audit(plugin_name, operation, target, True, "SYSTEM level access granted")
            return

        if write:
            self.require_level(
                plugin_name=plugin_name,
                permissions=permissions,
                required_level=PermissionLevel.WRITE,
                operation=operation,
                target=target,
            )
            allowed = permissions.can_write_path(path)
            reason = "Path allowed for write" if allowed else "Path is outside write allow-list"
        else:
            self.require_level(
                plugin_name=plugin_name,
                permissions=permissions,
                required_level=PermissionLevel.READ,
                operation=operation,
                target=target,
            )
            allowed = permissions.can_read_path(path)
            reason = "Path allowed for read" if allowed else "Path is outside read allow-list"

        self._audit(plugin_name, operation, target, allowed, reason)
        if not allowed:
            raise SecurityViolationError(reason)

    def check_network_access(
        self,
        plugin_name: str,
        permissions: PluginPermissions,
        domain: str,
    ) -> None:
        """Validate network permission and domain allow-list."""
        target = str(domain)
        operation = "network_access"

        if permissions.level == PermissionLevel.SYSTEM:
            self._audit(plugin_name, operation, target, True, "SYSTEM level access granted")
            return

        self.require_level(
            plugin_name=plugin_name,
            permissions=permissions,
            required_level=PermissionLevel.NETWORK,
            operation=operation,
            target=target,
        )
        allowed = permissions.can_access_domain(domain)
        reason = "Domain is in network allow-list" if allowed else "Domain is not in allow-list"
        self._audit(plugin_name, operation, target, allowed, reason)
        if not allowed:
            raise SecurityViolationError(reason)

    def check_env_var_access(
        self,
        plugin_name: str,
        permissions: PluginPermissions,
        env_var_name: str,
    ) -> None:
        """Validate environment variable access."""
        operation = "environment_read"
        target = str(env_var_name)

        if permissions.level == PermissionLevel.SYSTEM:
            self._audit(plugin_name, operation, target, True, "SYSTEM level access granted")
            return

        self.require_level(
            plugin_name=plugin_name,
            permissions=permissions,
            required_level=PermissionLevel.READ,
            operation=operation,
            target=target,
        )
        allowed = permissions.can_access_env_var(env_var_name)
        reason = "Environment variable is allow-listed" if allowed else "Environment variable is not allow-listed"
        self._audit(plugin_name, operation, target, allowed, reason)
        if not allowed:
            raise SecurityViolationError(reason)

    def check_process_creation(self, plugin_name: str, permissions: PluginPermissions) -> None:
        """Validate process creation permission."""
        operation = "process_creation"
        target = "subprocess"
        allowed = permissions.level == PermissionLevel.SYSTEM
        reason = (
            "SYSTEM level permits process creation"
            if allowed
            else "Process creation is forbidden outside SYSTEM level"
        )
        self._audit(plugin_name, operation, target, allowed, reason)
        if not allowed:
            raise SecurityViolationError(reason)

    def get_audit_events(self, plugin_name: Optional[str] = None) -> list[SecurityAuditEvent]:
        """Return audit events, optionally filtered by plugin name."""
        with self._lock:
            events = list(self._audit_events)
        if plugin_name is None:
            return events
        return [event for event in events if event.plugin_name == plugin_name]

    def clear_audit_events(self) -> None:
        """Reset audit log."""
        with self._lock:
            self._audit_events.clear()

    @staticmethod
    def _has_level(current: PermissionLevel, required: PermissionLevel) -> bool:
        return PERMISSION_ORDER[current] >= PERMISSION_ORDER[required]

    def _audit(
        self,
        plugin_name: str,
        operation: str,
        target: str,
        allowed: bool,
        reason: str,
    ) -> None:
        event = SecurityAuditEvent(
            timestamp=datetime.now(timezone.utc),
            plugin_name=plugin_name,
            operation=operation,
            target=target,
            allowed=allowed,
            reason=reason,
        )
        with self._lock:
            self._audit_events.append(event)

        log_method = self._logger.info if allowed else self._logger.warning
        log_method(
            "plugin_security_check",
            extra={
                "plugin_name": plugin_name,
                "operation": operation,
                "target": target,
                "allowed": allowed,
                "reason": reason,
            },
        )
