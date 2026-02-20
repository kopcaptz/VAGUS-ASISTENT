"""Фабрика создания экземпляров провайдеров из конфигурации."""

import os
import threading
import time
from typing import Dict, Any, Optional
from .base_provider import LLMProvider
from .provider_registry import ProviderRegistry
from ...layer0.logging import get_logger
from ...security import KeyManager


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
        self._key_manager = KeyManager()
        self._key_cache_ttl_seconds = 300.0
        self._key_cache_lock = threading.RLock()
        self._key_cache: dict[str, tuple[str, float]] = {}

    def invalidate_key_cache(self, provider_id: Optional[str] = None) -> None:
        with self._key_cache_lock:
            if provider_id is None:
                self._key_cache.clear()
                return
            self._key_cache.pop(provider_id.strip().lower(), None)

    def _resolve_api_key(self, provider_id: str, api_key: Optional[str]) -> str:
        if api_key is not None and str(api_key).strip():
            return str(api_key)

        provider_key = provider_id.strip().lower()
        now = time.monotonic()
        with self._key_cache_lock:
            cached = self._key_cache.get(provider_key)
            if cached is not None:
                value, expires_at = cached
                if now < expires_at:
                    return value
                self._key_cache.pop(provider_key, None)

        # KeyManager itself supports env override; explicit env fallback is preserved.
        resolved = self._key_manager.get_key(provider_id)
        if not resolved:
            env_key = f"{provider_id.upper().replace('-', '_')}_API_KEY"
            resolved = os.getenv(env_key, "")

        with self._key_cache_lock:
            self._key_cache[provider_key] = (resolved or "", now + self._key_cache_ttl_seconds)
        return resolved or ""

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
        api_key = self._resolve_api_key(provider_id, api_key)

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
        api_key = self._resolve_api_key(provider_id, api_key)

        model = model or (config.get("models") or ["gpt-4"])[0]
        timeout = config.get("timeout", 30)
        endpoint = config.get("endpoint")
        if endpoint:
            kwargs = {"timeout": timeout, "base_url": str(endpoint)}
        else:
            kwargs = {"timeout": timeout}

        return self.create(provider_id=provider_id, model=model, api_key=api_key, **kwargs)
