"""
Базовый класс провайдера LLM.
Все конкретные провайдеры (OpenAI, Anthropic и т.д.) наследуются от этого класса.
Основано на реализации Manus AI.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, Optional
from datetime import datetime
from ...layer0.logging import get_logger


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

    @abstractmethod
    async def request(
        self,
        prompt: str,
        stream: bool = False,
        **kwargs
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
        pass

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
        metadata: Optional[Dict[str, Any]] = None
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
            "timestamp": self.timestamp.isoformat()
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
        metadata: Optional[Dict[str, Any]] = None
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
        # Базовая реализация - должна быть переопределена в конкретных провайдерах
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
                "total": self.prompt_tokens + self.completion_tokens
            },
            "latency": self.latency,
            "cost": self.cost,
            "success": self.success,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }
        
    def __str__(self) -> str:
        status = "✅" if self.success else "❌"
        return f"{status} {self.provider_name}: {len(self.content)} chars, {self.latency:.2f}s, ${self.cost:.6f}"