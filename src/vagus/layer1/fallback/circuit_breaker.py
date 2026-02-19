"""
Реализация паттерна Circuit Breaker для защиты от каскадных сбоев.
Основано на реализации Manus AI.
"""

import time
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Any, Dict
from ...layer0.logging import get_logger


class CircuitBreakerState(Enum):
    """Состояния Circuit Breaker."""
    CLOSED = "CLOSED"      # Нормальная работа
    OPEN = "OPEN"          # Цепь разомкнута, запросы блокируются
    HALF_OPEN = "HALF_OPEN"  # Пробный режим восстановления


class CircuitBreakerOpenError(Exception):
    """Исключение, возникающее при попытке вызова с открытым Circuit Breaker."""
    pass


class CircuitBreaker:
    """Реализация паттерна Circuit Breaker для защиты от каскадных сбоев."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: int = 60,
        half_open_max_requests: int = 3
    ):
        """
        Инициализация Circuit Breaker.
        
        Args:
            failure_threshold: Порог ошибок для перехода в OPEN
            recovery_timeout: Время восстановления в секундах
            half_open_max_requests: Максимум запросов в HALF_OPEN состоянии
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_requests = half_open_max_requests
        
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._total_failure_count = 0
        self._total_success_count = 0
        self._last_failure_time: float = 0
        self._last_failure_wall_time: float = 0
        self._half_open_attempts = 0
        
        self.logger = get_logger("circuit_breaker")
        self.logger.info(
            f"CircuitBreaker инициализирован (threshold: {failure_threshold}, "
            f"recovery: {recovery_timeout}s)"
        )

    @property
    def state(self) -> CircuitBreakerState:
        """
        Возвращает текущее состояние.
        Автоматически переходит в HALF_OPEN при истечении таймаута.
        """
        if (
            self._state == CircuitBreakerState.OPEN
            and (time.monotonic() - self._last_failure_time) > self.recovery_timeout
        ):
            self._state = CircuitBreakerState.HALF_OPEN
            self._half_open_attempts = 0
            self._success_count = 0
            self.logger.info("Circuit Breaker: OPEN → HALF_OPEN (таймаут восстановления истёк)")
        
        return self._state

    def is_open(self) -> bool:
        """
        Проверяет, открыт ли Circuit Breaker.
        
        Returns:
            True если состояние OPEN
        """
        return self.state == CircuitBreakerState.OPEN

    def is_closed(self) -> bool:
        """
        Проверяет, закрыт ли Circuit Breaker.
        
        Returns:
            True если состояние CLOSED
        """
        return self.state == CircuitBreakerState.CLOSED

    def is_half_open(self) -> bool:
        """
        Проверяет, находится ли Circuit Breaker в HALF_OPEN состоянии.
        
        Returns:
            True если состояние HALF_OPEN
        """
        return self.state == CircuitBreakerState.HALF_OPEN

    async def call(self, func: Callable) -> Any:
        """
        Выполняет функцию, обернутую в Circuit Breaker.
        
        Args:
            func: Функция для выполнения
            
        Returns:
            Результат выполнения функции
            
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
            Exception: Любое исключение из функции
        """
        if self.state == CircuitBreakerState.OPEN:
            error_msg = f"Circuit Breaker открыт. Пропускаем вызов."
            self.logger.warning(error_msg)
            raise CircuitBreakerOpenError(error_msg)
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            if self._half_open_attempts >= self.half_open_max_requests:
                error_msg = f"Достигнут лимит попыток в HALF_OPEN состоянии"
                self.logger.warning(error_msg)
                raise CircuitBreakerOpenError(error_msg)
            self._half_open_attempts += 1
            self.logger.debug(f"HALF_OPEN попытка {self._half_open_attempts}/{self.half_open_max_requests}")

        try:
            result = await func()
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    def _on_success(self) -> None:
        """Обработка успешного вызова."""
        self._total_success_count += 1
        if self.state == CircuitBreakerState.HALF_OPEN:
            self._success_count += 1
            self.logger.debug(f"HALF_OPEN успех {self._success_count}/{self.half_open_max_requests}")
            
            if self._success_count >= self.half_open_max_requests:
                self._state = CircuitBreakerState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                self._half_open_attempts = 0
                self.logger.info("Circuit Breaker: HALF_OPEN → CLOSED (успешные попытки)")
        
        elif self.state == CircuitBreakerState.CLOSED:
            # Сбрасываем счётчик ошибок при успешном вызове
            if self._failure_count > 0:
                self._failure_count = 0
                self.logger.debug("Счётчик ошибок сброшен после успешного вызова")

    def _on_failure(self) -> None:
        """Обработка неудачного вызова."""
        self._failure_count += 1
        self._total_failure_count += 1
        self._last_failure_time = time.monotonic()
        self._last_failure_wall_time = time.time()
        
        if self.state == CircuitBreakerState.CLOSED and self._failure_count >= self.failure_threshold:
            self._state = CircuitBreakerState.OPEN
            self.logger.warning(
                f"Circuit Breaker: CLOSED → OPEN "
                f"(достигнут порог ошибок: {self._failure_count}/{self.failure_threshold})"
            )
        
        elif self.state == CircuitBreakerState.HALF_OPEN:
            self._state = CircuitBreakerState.OPEN
            self.logger.warning("Circuit Breaker: HALF_OPEN → OPEN (ошибка в пробном режиме)")

    def get_stats(self) -> Dict[str, Any]:
        """
        Возвращает статистику Circuit Breaker.
        
        Returns:
            Словарь со статистикой
        """
        return {
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "total_failure_count": self._total_failure_count,
            "total_success_count": self._total_success_count,
            "half_open_attempts": self._half_open_attempts,
            "last_failure_time": self._last_failure_time,
            "last_failure_iso": (
                datetime.fromtimestamp(self._last_failure_wall_time, tz=timezone.utc).isoformat()
                if self._last_failure_wall_time > 0
                else None
            ),
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "half_open_max_requests": self.half_open_max_requests,
            "time_since_last_failure": time.monotonic() - self._last_failure_time if self._last_failure_time > 0 else 0,
            "success_rate": (
                (self._total_success_count / (self._total_success_count + self._total_failure_count)) * 100.0
                if (self._total_success_count + self._total_failure_count) > 0
                else 100.0
            ),
        }

    def reset(self) -> None:
        """Полностью сбрасывает Circuit Breaker."""
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._total_failure_count = 0
        self._total_success_count = 0
        self._half_open_attempts = 0
        self._last_failure_time = 0
        self._last_failure_wall_time = 0
        self.logger.info("Circuit Breaker сброшен")

    def __str__(self) -> str:
        """Строковое представление."""
        return f"CircuitBreaker(state={self.state.value}, failures={self._failure_count})"