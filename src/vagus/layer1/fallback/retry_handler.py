"""
Configurable retry handler with exponential backoff.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

from ...layer0.logging import get_logger

T = TypeVar("T")


@dataclass(slots=True)
class RetryConfig:
    max_attempts: int = 5
    backoff_factor: float = 2.0
    retryable_errors: list[str] = field(
        default_factory=lambda: ["timeout", "rate_limit", "network_error"]
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RetryConfig":
        if not isinstance(data, dict):
            return cls()
        max_attempts = data.get("max_attempts", 5)
        backoff_factor = data.get("backoff_factor", 2.0)
        retryable_errors = data.get("retryable_errors", ["timeout", "rate_limit", "network_error"])
        try:
            parsed_attempts = int(max_attempts)
        except (TypeError, ValueError):
            parsed_attempts = 5
        if parsed_attempts < 1:
            parsed_attempts = 1
        try:
            parsed_factor = float(backoff_factor)
        except (TypeError, ValueError):
            parsed_factor = 2.0
        if parsed_factor < 1.0:
            parsed_factor = 1.0
        parsed_errors = []
        if isinstance(retryable_errors, list):
            for item in retryable_errors:
                if isinstance(item, str) and item.strip():
                    parsed_errors.append(item.strip().lower())
        if not parsed_errors:
            parsed_errors = ["timeout", "rate_limit", "network_error"]
        return cls(
            max_attempts=parsed_attempts,
            backoff_factor=parsed_factor,
            retryable_errors=parsed_errors,
        )


class RetryHandler:
    """
    Automatic retry with exponential backoff:
    1s, 2s, 4s, 8s, 16s (defaults).
    """

    def __init__(
        self,
        config: RetryConfig | None = None,
        *,
        base_delay_seconds: float = 1.0,
        sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.config = config or RetryConfig()
        self.base_delay_seconds = max(0.0, float(base_delay_seconds))
        self.sleep_func = sleep_func
        self.logger = get_logger("fallback.retry_handler")

    def _error_text(self, exc: Exception) -> str:
        return f"{type(exc).__name__}: {exc}".lower()

    def is_retryable(self, exc: Exception) -> bool:
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return True
        text = self._error_text(exc)
        return any(keyword in text for keyword in self.config.retryable_errors)

    def backoff_delay(self, retry_attempt: int) -> float:
        # retry_attempt starts from 1 (first retry after first failure)
        exponent = max(0, int(retry_attempt) - 1)
        return self.base_delay_seconds * (self.config.backoff_factor ** exponent)

    async def execute(self, func: Callable[[], Awaitable[T]]) -> T:
        last_exc: Exception | None = None
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                return await func()
            except Exception as exc:
                last_exc = exc
                is_last_attempt = attempt >= self.config.max_attempts
                retryable = self.is_retryable(exc)
                if is_last_attempt or not retryable:
                    raise
                delay = self.backoff_delay(attempt)
                self.logger.warning(
                    "Retry attempt %s/%s after error: %s. Backoff %.2fs",
                    attempt + 1,
                    self.config.max_attempts,
                    exc,
                    delay,
                )
                await self.sleep_func(delay)
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Retry execution failed unexpectedly")


__all__ = ["RetryConfig", "RetryHandler"]
