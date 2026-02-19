"""
Обработчик fallback: CircuitBreaker + RetryManager + цепочка провайдеров.
"""

from typing import List, Callable, Awaitable, Any, Dict, Optional
from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from .retry_manager import RetryManager
from .retry_handler import RetryConfig, RetryHandler
from ...layer0.logging import get_logger


class FallbackHandler:
    """
    Управляет цепочкой fallback с Circuit Breaker и retry.
    При CircuitBreakerOpenError или ошибке провайдера — переключение на следующий.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: int = 60,
        max_retries: int = 3,
        base_delay: float = 1.0,
        retry_config: Optional[Dict[str, Any]] = None,
        retry_handler: Optional[RetryHandler] = None,
    ):
        """
        Инициализация FallbackHandler.

        Args:
            failure_threshold: Порог ошибок для Circuit Breaker
            recovery_timeout: Таймаут восстановления Circuit Breaker
            max_retries: Максимум retry на одного провайдера
            base_delay: Базовая задержка для exponential backoff
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.retry_manager = RetryManager(
            max_retries=max_retries,
            base_delay=base_delay,
        )
        resolved_retry_config = RetryConfig.from_dict(retry_config)
        # Keep old "max_retries" behavior compatible if explicit config is not passed.
        if retry_config is None:
            resolved_retry_config.max_attempts = max(1, int(max_retries))
        self.retry_handler = retry_handler or RetryHandler(
            config=resolved_retry_config,
            base_delay_seconds=base_delay,
        )
        self.logger = get_logger("fallback.handler")
        self.logger.info(
            f"FallbackHandler инициализирован (threshold={failure_threshold}, "
            f"retries={self.retry_handler.config.max_attempts})"
        )

    def _get_circuit_breaker(self, provider_id: str) -> CircuitBreaker:
        """Возвращает Circuit Breaker для провайдера (создаёт при необходимости)."""
        if provider_id not in self._circuit_breakers:
            self._circuit_breakers[provider_id] = CircuitBreaker(
                failure_threshold=self.failure_threshold,
                recovery_timeout=self.recovery_timeout,
            )
        return self._circuit_breakers[provider_id]

    async def execute(
        self,
        provider_ids: List[str],
        request_func: Callable[[str], Awaitable[Any]],
        provider_getter: Optional[Callable[[str], Any]] = None,
    ) -> Any:
        """
        Выполняет запрос по цепочке провайдеров до первого успеха.

        Args:
            provider_ids: Список ID провайдеров в порядке приоритета
            request_func: Функция (provider_id) -> Awaitable, выполняющая запрос
            provider_getter: Опционально, (provider_id) -> провайдер (для проверки available)

        Returns:
            Результат request_func

        Raises:
            Exception: Последняя ошибка после исчерпания цепочки
        """
        last_error: Optional[Exception] = None

        for provider_id in provider_ids:
            # Проверка доступности провайдера
            if provider_getter:
                provider = provider_getter(provider_id)
                if provider is None or (hasattr(provider, "is_available") and not provider.is_available()):
                    self.logger.debug(f"Provider {provider_id} unavailable, skipping")
                    continue

            cb = self._get_circuit_breaker(provider_id)

            if cb.is_open():
                self.logger.info(f"Circuit open for {provider_id}, trying next provider")
                continue

            def _make_request(pid: str):
                async def _do_request() -> Any:
                    async def _call() -> Any:
                        return await request_func(pid)
                    return await cb.call(_call)
                return _do_request

            try:
                result = await self.retry_handler.execute(
                    _make_request(provider_id)
                )
                return (result, provider_id)
            except CircuitBreakerOpenError as e:
                last_error = e
                self.logger.warning(f"CircuitBreakerOpen for {provider_id}: {e}")
                continue
            except Exception as e:
                last_error = e
                self.logger.warning(f"Request failed for {provider_id}: {e}")
                continue

        if last_error is not None:
            raise last_error
        raise RuntimeError(
            f"No successful provider in chain: {provider_ids}. "
            "All circuits may be open or providers unavailable."
        )
