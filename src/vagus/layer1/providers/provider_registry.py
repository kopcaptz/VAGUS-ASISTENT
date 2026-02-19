"""
Реестр провайдеров LLM (плагинная система).
"""

from typing import Dict, Type, Optional, List
from .base_provider import LLMProvider
from ...layer0.logging import get_logger


class ProviderRegistry:
    """Реестр классов провайдеров."""

    def __init__(self):
        self._registry: Dict[str, Type[LLMProvider]] = {}
        self.logger = get_logger("providers.registry")

    def register(self, name: str, provider_class: Type[LLMProvider]) -> None:
        """Регистрирует класс провайдера."""
        if not issubclass(provider_class, LLMProvider):
            raise TypeError(f"{provider_class} must inherit from LLMProvider")
        self._registry[name] = provider_class
        self.logger.debug(f"Provider class registered: {name}")

    def get_class(self, name: str) -> Type[LLMProvider]:
        """Возвращает класс провайдера по имени."""
        if name not in self._registry:
            raise KeyError(f"Provider '{name}' not found. Available: {list(self._registry.keys())}")
        return self._registry[name]

    def list_providers(self) -> List[str]:
        """Возвращает список зарегистрированных провайдеров."""
        return list(self._registry.keys())

    def has(self, name: str) -> bool:
        """Проверяет наличие провайдера."""
        return name in self._registry
