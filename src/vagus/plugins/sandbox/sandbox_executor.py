"""Sandbox execution primitives for plugins."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field


class SandboxLimits(BaseModel):
    """Execution limits for plugin sandbox."""

    enabled: bool = Field(default=True)
    memory_limit_mb: int = Field(default=512, ge=64, le=16384)
    timeout_seconds: int = Field(default=30, ge=1, le=3600)


class SandboxExecutionError(RuntimeError):
    """Raised when sandbox execution fails or times out."""


class SandboxExecutor:
    """Timeout-guarded plugin executor.

    Note:
        This is a safe baseline abstraction. It enforces timeouts but does not
        yet provide hard OS-level memory/process isolation.
    """

    def __init__(self, limits: Optional[SandboxLimits] = None) -> None:
        self.limits = limits or SandboxLimits()

    def execute(self, callback: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute callback with configured sandbox policy."""
        if not callable(callback):
            raise TypeError("Sandbox callback must be callable")

        if not self.limits.enabled:
            return callback(*args, **kwargs)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(callback, *args, **kwargs)
            try:
                return future.result(timeout=self.limits.timeout_seconds)
            except FutureTimeoutError as exc:
                future.cancel()
                raise SandboxExecutionError(
                    f"Plugin execution exceeded {self.limits.timeout_seconds} seconds"
                ) from exc
