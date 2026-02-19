"""
Менеджер повторных попыток с exponential backoff.
"""

import asyncio
from typing import Callable, Awaitable, TypeVar, Any
from ...layer0.logging import get_logger

T = TypeVar("T")


class RetryManager:
    """Exponential backoff: 1s -> 2s -> 4s -> 8s."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ):
        """
        Инициализация менеджера повторных попыток.

        Args:
            max_retries: Максимум попыток (включая первую)
            base_delay: Базовая задержка в секундах
            max_delay: Максимальная задержка в секундах
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.logger = get_logger("fallback.retry")

    async def execute_with_retry(
        self,
        coro_func: Callable[[], Awaitable[T]],
        *,
        retry_on_exceptions: tuple = (Exception,),
    ) -> T:
        """
        Выполняет корутину с повторными попытками и exponential backoff.

        Args:
            coro_func: Функция без аргументов, возвращающая корутину
            retry_on_exceptions: Tuple исключений, при которых делать retry

        Returns:
            Результат корутины

        Raises:
            Последнее исключение после исчерпания попыток
        """
        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                return await coro_func()
            except retry_on_exceptions as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = min(
                        self.base_delay * (2 ** attempt),
                        self.max_delay,
                    )
                    self.logger.warning(
                        f"Attempt {attempt + 1}/{self.max_retries} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(
                        f"All {self.max_retries} attempts failed. Last error: {e}"
                    )

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("Retry exhausted without exception")
