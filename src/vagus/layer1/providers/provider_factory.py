"""
Фабрика создания экземпляров провайдеров из конфигурации.
"""

import os
from typing import Dict, Any, Optional
from .base_provider import LLMProvider
from .provider_registry import ProviderRegistry
from ...layer0.logging import get_logger


def _create_default_registry() -> ProviderRegistry:
    """Создаёт реестр с зарегистрированными провайдерами по умолчанию."""
    from .openai_provider import OpenAIProvider
    from .anthropic_provider import AnthropicProvider
    from .deepseek_provider import DeepSeekProvider
    from .openrouter_provider import OpenRouterProvider
    from .google_provider import GoogleProvider
    r = ProviderRegistry()
    r.register("openai", OpenAIProvider)
    r.register("anthropic", AnthropicProvider)
    r.register("deepseek", DeepSeekProvider)
    r.register("openrouter", OpenRouterProvider)
    r.register("google", GoogleProvider)
    return r


class ProviderFactory:
    """Создаёт экземпляры провайдеров из конфигурации."""

    def __init__(self, registry: Optional[ProviderRegistry] = None):
        self.registry = registry or _create_default_registry()
        self.logger = get_logger("providers.factory")

    def create(
        self,
        provider_id: str,
        model: str,
        api_key: Optional[str] = None,
        **kwargs,
    ) -> LLMProvider:
        """
        Создаёт экземпляр провайдера.

        Args:
            provider_id: Имя провайдера (openai, anthropic, deepseek, ...)
            model: Модель
            api_key: API ключ (или из env: {PROVIDER_ID}_API_KEY)
            **kwargs: Дополнительные параметры (timeout, endpoint, ...)

        Returns:
            Экземпляр LLMProvider
        """
        if api_key is None:
            env_key = f"{provider_id.upper().replace('-', '_')}_API_KEY"
            api_key = os.getenv(env_key, "")

        provider_class = self.registry.get_class(provider_id)
        instance = provider_class(
            name=provider_id,
            model=model,
            api_key=api_key,
            **kwargs,
        )
        self.logger.info(f"Provider created: {provider_id}:{model}")
        return instance

    def create_from_config(
        self,
        config: Dict[str, Any],
        provider_id: str,
        model: Optional[str] = None,
    ) -> LLMProvider:
        """
        Создаёт провайдера из конфигурации (AppConfig.providers или аналог).

        Args:
            config: Словарь конфигурации провайдера (endpoint, timeout, models, api_key, ...)
            provider_id: Имя провайдера
            model: Модель (если не указано — первая из config.models или default)
        """
        api_key = config.get("api_key")
        if hasattr(api_key, "get_secret_value"):
            api_key = api_key.get_secret_value()
        elif api_key is None:
            env_key = f"{provider_id.upper().replace('-', '_')}_API_KEY"
            api_key = os.getenv(env_key, "")

        model = model or (config.get("models") or ["gpt-4"])[0]
        timeout = config.get("timeout", 30)
        endpoint = config.get("endpoint")
        if endpoint:
            kwargs = {"timeout": timeout, "base_url": str(endpoint)}
        else:
            kwargs = {"timeout": timeout}

        return self.create(provider_id=provider_id, model=model, api_key=api_key, **kwargs)
