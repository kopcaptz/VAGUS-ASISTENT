"""
Базовый модуль провайдеров LLM и shared HTTP client pool.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any, Dict, Optional, AsyncGenerator

import httpx

from ...layer0.logging import get_logger


@dataclass(frozen=True)
class HTTPClientPoolConfig:
    """Конфигурация пула HTTP-соединений."""

    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: float = 5.0


class HTTPClientManager:
    """
    Singleton-менеджер shared httpx.AsyncClient.

    Используется всеми LLM-провайдерами для переиспользования TCP-соединений.
    """

    _logger = get_logger("providers.http_pool")
    _lock: Lock = Lock()
    _config: HTTPClientPoolConfig = HTTPClientPoolConfig()
    _client: Optional[httpx.AsyncClient] = None
    _retired_clients: list[httpx.AsyncClient] = []

    @classmethod
    def configure(cls, *, config: Optional[HTTPClientPoolConfig] = None, **kwargs) -> HTTPClientPoolConfig:
        """Обновляет конфигурацию пула и сбрасывает текущий клиент при изменениях."""
        next_config = config or HTTPClientPoolConfig(**kwargs)
        if next_config.max_connections < 1:
            next_config = HTTPClientPoolConfig(
                max_connections=1,
                max_keepalive_connections=max(1, next_config.max_keepalive_connections),
                keepalive_expiry=max(0.0, next_config.keepalive_expiry),
            )

        with cls._lock:
            if next_config == cls._config:
                return cls._config
            cls._config = next_config
            if cls._client is not None:
                cls._retired_clients.append(cls._client)
                cls._client = None

        cls._logger.info(
            "HTTP pool configured: max_connections=%s max_keepalive_connections=%s keepalive_expiry=%ss",
            next_config.max_connections,
            next_config.max_keepalive_connections,
            next_config.keepalive_expiry,
        )
        return next_config

    @classmethod
    def current_config(cls) -> HTTPClientPoolConfig:
        """Возвращает текущую конфигурацию пула."""
        return cls._config

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        """Возвращает shared AsyncClient с connection pooling."""
        with cls._lock:
            if cls._client is not None and not cls._client.is_closed:
                return cls._client

            limits = httpx.Limits(
                max_connections=cls._config.max_connections,
                max_keepalive_connections=cls._config.max_keepalive_connections,
                keepalive_expiry=cls._config.keepalive_expiry,
            )
            # Общий timeout: провайдеры при необходимости переопределяют timeout на SDK уровне.
            timeout = httpx.Timeout(timeout=30.0, connect=10.0)
            cls._client = httpx.AsyncClient(limits=limits, timeout=timeout)
            return cls._client

    @classmethod
    async def close(cls) -> None:
        """Закрывает активный и устаревшие HTTP-клиенты."""
        with cls._lock:
            clients: list[httpx.AsyncClient] = []
            if cls._client is not None:
                clients.append(cls._client)
                cls._client = None
            if cls._retired_clients:
                clients.extend(cls._retired_clients)
                cls._retired_clients = []

        for client in clients:
            try:
                if not client.is_closed:
                    await client.aclose()
            except Exception as exc:
                cls._logger.warning("Failed to close HTTP client: %s", exc)

    @classmethod
    def get_pool_stats(cls) -> Dict[str, Any]:
        """Возвращает диагностику пула."""
        with cls._lock:
            return {
                "configured": {
                    "max_connections": cls._config.max_connections,
                    "max_keepalive_connections": cls._config.max_keepalive_connections,
                    "keepalive_expiry": cls._config.keepalive_expiry,
                },
                "client_active": cls._client is not None and not cls._client.is_closed,
                "retired_clients": len(cls._retired_clients),
            }


class LLMProvider(ABC):
    """Абстрактный базовый класс для всех LLM-провайдеров."""

    def __init__(self, name: str, model: str, api_key: str, timeout: int = 30, **kwargs):
        """
        Инициализация провайдера.

        Args:
            name: Имя провайдера (например, "openai", "anthropic")
            model: Идентификатор модели
            api_key: API ключ
            timeout: Таймаут запроса в секундах
            **kwargs: Дополнительные параметры
        """
        self.name = name
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.extra_params = kwargs
        self.logger = get_logger(f"provider.{name}")
        self.is_enabled = True

        self.logger.info(f"Провайдер инициализирован: {name} ({model})")

    @classmethod
    def configure_http_client_pool(
        cls,
        *,
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
        keepalive_expiry: float = 5.0,
    ) -> None:
        """Глобально настраивает shared HTTP pool для всех провайдеров."""
        HTTPClientManager.configure(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=keepalive_expiry,
        )

    @classmethod
    async def close_shared_http_client(cls) -> None:
        """Закрывает shared HTTP pool при graceful shutdown."""
        await HTTPClientManager.close()

    def get_shared_http_client(self) -> httpx.AsyncClient:
        """Возвращает singleton AsyncClient с connection pooling."""
        return HTTPClientManager.get_client()

    @abstractmethod
    async def request(
        self,
        prompt: str,
        stream: bool = False,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Отправляет запрос к LLM.

        Args:
            prompt: Текст запроса
            stream: Режим стриминга
            **kwargs: Дополнительные параметры

        Yields:
            Словари с чанками ответа
        """
        yield {}

    @abstractmethod
    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """
        Расчёт стоимости запроса.

        Args:
            prompt_tokens: Количество токенов в промпте
            completion_tokens: Количество токенов в ответе

        Returns:
            Стоимость в USD
        """
        raise NotImplementedError

    def enable(self) -> None:
        """Включает провайдера."""
        self.is_enabled = True
        self.logger.info(f"Провайдер включён: {self.name}")

    def disable(self) -> None:
        """Отключает провайдера."""
        self.is_enabled = False
        self.logger.info(f"Провайдер отключён: {self.name}")

    def is_available(self) -> bool:
        """
        Проверяет доступность провайдера.

        Returns:
            True если провайдер доступен
        """
        return self.is_enabled and self.api_key is not None

    def get_info(self) -> Dict[str, Any]:
        """
        Возвращает информацию о провайдере.

        Returns:
            Словарь с информацией
        """
        return {
            "name": self.name,
            "model": self.model,
            "enabled": self.is_enabled,
            "available": self.is_available(),
            "timeout": self.timeout,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', model='{self.model}')"

    def __str__(self) -> str:
        return f"{self.name}:{self.model}"


class LLMRequest:
    """Модель запроса к LLM."""

    def __init__(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        stream: bool = False,
        priority: str = "normal",
        interactive: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.prompt = prompt
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
        self.priority = priority
        self.interactive = interactive
        self.metadata = metadata or {}
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует запрос в словарь."""
        return {
            "prompt": self.prompt,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": self.stream,
            "priority": self.priority,
            "interactive": self.interactive,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class LLMResponse:
    """Модель ответа от LLM."""

    def __init__(
        self,
        content: str,
        provider_name: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency: float,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.content = content
        self.provider_name = provider_name
        self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.latency = latency
        self.success = success
        self.error_message = error_message
        self.metadata = metadata or {}
        self.timestamp = datetime.now()
        self.cost = self._calculate_cost()

    def _calculate_cost(self) -> float:
        """Расчёт стоимости ответа."""
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Конвертирует ответ в словарь."""
        return {
            "content": self.content,
            "provider": self.provider_name,
            "model": self.model,
            "tokens": {
                "prompt": self.prompt_tokens,
                "completion": self.completion_tokens,
                "total": self.prompt_tokens + self.completion_tokens,
            },
            "latency": self.latency,
            "cost": self.cost,
            "success": self.success,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    def __str__(self) -> str:
        status = "✅" if self.success else "❌"
        return (
            f"{status} {self.provider_name}: {len(self.content)} chars, "
            f"{self.latency:.2f}s, ${self.cost:.6f}"
        )


__all__ = [
    "HTTPClientPoolConfig",
    "HTTPClientManager",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
]
