"""Sandbox execution engine with security restrictions."""

from __future__ import annotations

import asyncio
import builtins
import inspect
import os
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
import socket
import subprocess
from typing import Any, Callable, Iterator, Optional

from ..core.models import LoadedPlugin, PermissionLevel, PluginPermissions
from .security_manager import SecurityManager, SecurityViolationError

try:
    import resource

    _RESOURCE_AVAILABLE = True
except Exception:  # pragma: no cover - platform dependent
    resource = None  # type: ignore[assignment]
    _RESOURCE_AVAILABLE = False


class SandboxExecutionError(RuntimeError):
    """Raised when sandboxed execution fails."""


@dataclass
class SandboxPolicy:
    """Global sandbox policy from application config."""

    enabled: bool = True
    memory_limit_mb: int = 512
    timeout_seconds: int = 30
    filesystem_whitelist: list[str] = field(default_factory=list)
    network_whitelist: list[str] = field(default_factory=list)

    def normalized_filesystem_whitelist(self) -> list[str]:
        return [str(Path(path).expanduser().resolve()) for path in self.filesystem_whitelist]

    def normalized_network_whitelist(self) -> list[str]:
        return [domain.strip().lower() for domain in self.network_whitelist if domain.strip()]


class SandboxEngine:
    """Secure runtime for plugin callback execution."""

    def __init__(
        self,
        policy: Optional[SandboxPolicy] = None,
        security_manager: Optional[SecurityManager] = None,
    ) -> None:
        self.policy = policy or SandboxPolicy()
        self.security_manager = security_manager or SecurityManager()

    async def execute_async(
        self,
        plugin: str | LoadedPlugin,
        callback: Callable[..., Any],
        *args: Any,
        permissions: Optional[PluginPermissions] = None,
        **kwargs: Any,
    ) -> Any:
        """Execute callback in sandbox with timeout and restrictions."""
        if not callable(callback):
            raise TypeError("Sandbox callback must be callable")

        plugin_name, plugin_permissions = self._resolve_plugin_and_permissions(plugin, permissions)
        if not self.policy.enabled:
            return await self._invoke_callback(callback, *args, **kwargs)

        timeout_seconds = min(
            self.policy.timeout_seconds,
            plugin_permissions.max_execution_time_seconds,
        )
        memory_limit_mb = min(
            self.policy.memory_limit_mb,
            plugin_permissions.max_memory_mb,
        )

        try:
            with self._sandbox_context(plugin_name, plugin_permissions, memory_limit_mb):
                async with asyncio.timeout(timeout_seconds):
                    return await self._invoke_callback(callback, *args, **kwargs)
        except TimeoutError as exc:
            raise SandboxExecutionError(
                f"Plugin '{plugin_name}' exceeded timeout of {timeout_seconds} seconds"
            ) from exc

    def execute(
        self,
        plugin: str | LoadedPlugin,
        callback: Callable[..., Any],
        *args: Any,
        permissions: Optional[PluginPermissions] = None,
        **kwargs: Any,
    ) -> Any:
        """Synchronous wrapper over async sandbox execution."""
        return asyncio.run(
            self.execute_async(
                plugin,
                callback,
                *args,
                permissions=permissions,
                **kwargs,
            )
        )

    async def _invoke_callback(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if inspect.iscoroutinefunction(callback):
            return await callback(*args, **kwargs)
        return await asyncio.to_thread(callback, *args, **kwargs)

    def _resolve_plugin_and_permissions(
        self,
        plugin: str | LoadedPlugin,
        permissions: Optional[PluginPermissions],
    ) -> tuple[str, PluginPermissions]:
        if isinstance(plugin, LoadedPlugin):
            plugin_name = plugin.name
            plugin_permissions = permissions or plugin.manifest.runtime_permissions
        else:
            plugin_name = plugin
            plugin_permissions = permissions or PluginPermissions()

        effective_permissions = plugin_permissions.model_copy(deep=True)
        # Global whitelist extends read paths only (read-only policy paths).
        global_read_paths = self.policy.normalized_filesystem_whitelist()
        effective_permissions.filesystem.read = sorted(
            set(effective_permissions.filesystem.read + global_read_paths)
        )
        return plugin_name, effective_permissions

    @contextmanager
    def _sandbox_context(
        self,
        plugin_name: str,
        permissions: PluginPermissions,
        memory_limit_mb: int,
    ) -> Iterator[None]:
        with ExitStack() as stack:
            stack.enter_context(self._apply_memory_limit(memory_limit_mb))
            stack.enter_context(self._patch_process_creation(plugin_name, permissions))
            stack.enter_context(self._patch_filesystem_access(plugin_name, permissions))
            stack.enter_context(self._patch_network_access(plugin_name, permissions))
            stack.enter_context(self._patch_environment_access(plugin_name, permissions))
            yield

    @contextmanager
    def _apply_memory_limit(self, memory_limit_mb: int) -> Iterator[None]:
        if not _RESOURCE_AVAILABLE:
            yield
            return

        limit_bytes = int(memory_limit_mb) * 1024 * 1024
        old_limits = resource.getrlimit(resource.RLIMIT_AS)
        hard_limit = old_limits[1]
        # In many restricted environments, lowering from unlimited hard limit can
        # be irreversible for the current process (cannot restore soft limit back).
        # To avoid poisoning host process limits, skip hard RLIMIT enforcement.
        if hard_limit == resource.RLIM_INFINITY:
            yield
            return

        soft_limit = limit_bytes if hard_limit == resource.RLIM_INFINITY else min(limit_bytes, hard_limit)
        try:
            resource.setrlimit(resource.RLIMIT_AS, (soft_limit, hard_limit))
        except (OSError, ValueError):
            # If limit cannot be applied, continue with timeout-based containment.
            yield
            return

        try:
            yield
        finally:
            try:
                resource.setrlimit(resource.RLIMIT_AS, old_limits)
            except (OSError, ValueError):
                pass

    @contextmanager
    def _patch_process_creation(
        self,
        plugin_name: str,
        permissions: PluginPermissions,
    ) -> Iterator[None]:
        if permissions.level == PermissionLevel.SYSTEM:
            yield
            return

        original_popen = subprocess.Popen
        original_run = subprocess.run
        original_check_call = subprocess.check_call
        original_check_output = subprocess.check_output
        original_call = subprocess.call
        original_system = os.system

        def _blocked_process_call(*_: Any, **__: Any) -> None:
            self.security_manager.check_process_creation(plugin_name, permissions)
            raise SecurityViolationError("Process creation is blocked by sandbox")

        subprocess.Popen = _blocked_process_call  # type: ignore[assignment]
        subprocess.run = _blocked_process_call  # type: ignore[assignment]
        subprocess.check_call = _blocked_process_call  # type: ignore[assignment]
        subprocess.check_output = _blocked_process_call  # type: ignore[assignment]
        subprocess.call = _blocked_process_call  # type: ignore[assignment]
        os.system = _blocked_process_call  # type: ignore[assignment]

        try:
            yield
        finally:
            subprocess.Popen = original_popen  # type: ignore[assignment]
            subprocess.run = original_run  # type: ignore[assignment]
            subprocess.check_call = original_check_call  # type: ignore[assignment]
            subprocess.check_output = original_check_output  # type: ignore[assignment]
            subprocess.call = original_call  # type: ignore[assignment]
            os.system = original_system  # type: ignore[assignment]

    @contextmanager
    def _patch_filesystem_access(
        self,
        plugin_name: str,
        permissions: PluginPermissions,
    ) -> Iterator[None]:
        original_open = builtins.open
        whitelist = self.policy.normalized_filesystem_whitelist()

        def _guarded_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any):  # noqa: ANN401
            if isinstance(file, int):
                return original_open(file, mode, *args, **kwargs)

            path = Path(file).expanduser().resolve()
            write = any(flag in mode for flag in ("w", "a", "x", "+"))

            if whitelist and not self._is_path_in_whitelist(path, whitelist):
                self.security_manager._audit(  # pylint: disable=protected-access
                    plugin_name,
                    "filesystem_policy",
                    str(path),
                    False,
                    "Path is outside sandbox filesystem whitelist",
                )
                raise SecurityViolationError("Path is outside sandbox filesystem whitelist")

            self.security_manager.check_filesystem_access(
                plugin_name=plugin_name,
                permissions=permissions,
                path=path,
                write=write,
            )
            return original_open(path, mode, *args, **kwargs)

        builtins.open = _guarded_open  # type: ignore[assignment]
        try:
            yield
        finally:
            builtins.open = original_open  # type: ignore[assignment]

    @contextmanager
    def _patch_network_access(
        self,
        plugin_name: str,
        permissions: PluginPermissions,
    ) -> Iterator[None]:
        original_getaddrinfo = socket.getaddrinfo
        original_create_connection = socket.create_connection
        original_socket_connect = socket.socket.connect
        global_whitelist = self.policy.normalized_network_whitelist()

        def _assert_domain_allowed(host: str) -> None:
            normalized_host = (host or "").strip().lower()
            if not normalized_host:
                raise SecurityViolationError("Network host must not be empty")

            if global_whitelist and not self._is_domain_allowed(normalized_host, global_whitelist):
                self.security_manager._audit(  # pylint: disable=protected-access
                    plugin_name,
                    "network_policy",
                    normalized_host,
                    False,
                    "Domain is outside sandbox network whitelist",
                )
                raise SecurityViolationError("Domain is outside sandbox network whitelist")

            self.security_manager.check_network_access(plugin_name, permissions, normalized_host)

        def _guarded_getaddrinfo(host: str, *args: Any, **kwargs: Any):
            _assert_domain_allowed(str(host))
            return original_getaddrinfo(host, *args, **kwargs)

        def _guarded_create_connection(address: tuple[str, int], *args: Any, **kwargs: Any):
            _assert_domain_allowed(str(address[0]))
            return original_create_connection(address, *args, **kwargs)

        def _guarded_socket_connect(sock: socket.socket, address: Any):
            host = address[0] if isinstance(address, tuple) and address else ""
            _assert_domain_allowed(str(host))
            return original_socket_connect(sock, address)

        socket.getaddrinfo = _guarded_getaddrinfo  # type: ignore[assignment]
        socket.create_connection = _guarded_create_connection  # type: ignore[assignment]
        socket.socket.connect = _guarded_socket_connect  # type: ignore[assignment]
        try:
            yield
        finally:
            socket.getaddrinfo = original_getaddrinfo  # type: ignore[assignment]
            socket.create_connection = original_create_connection  # type: ignore[assignment]
            socket.socket.connect = original_socket_connect  # type: ignore[assignment]

    @contextmanager
    def _patch_environment_access(
        self,
        plugin_name: str,
        permissions: PluginPermissions,
    ) -> Iterator[None]:
        original_getenv = os.getenv

        def _guarded_getenv(key: str, default: Any = None) -> Any:
            self.security_manager.check_env_var_access(plugin_name, permissions, key)
            return original_getenv(key, default)

        os.getenv = _guarded_getenv  # type: ignore[assignment]
        try:
            yield
        finally:
            os.getenv = original_getenv  # type: ignore[assignment]

    @staticmethod
    def _is_path_in_whitelist(path: Path, whitelist: list[str]) -> bool:
        for allowed_raw in whitelist:
            allowed_path = Path(allowed_raw).expanduser().resolve()
            if path == allowed_path or path.is_relative_to(allowed_path):
                return True
        return False

    @staticmethod
    def _is_domain_allowed(host: str, allowlist: list[str]) -> bool:
        for domain in allowlist:
            normalized = domain.strip().lower()
            if host == normalized or host.endswith(f".{normalized}"):
                return True
        return False
