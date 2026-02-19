"""
Модуль провайдеров LLM.
"""

from .base_provider import LLMProvider, LLMRequest, LLMResponse
from .provider_registry import ProviderRegistry
from .provider_factory import ProviderFactory
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider
from .deepseek_provider import DeepSeekProvider
from .openrouter_provider import OpenRouterProvider
from .google_provider import GoogleProvider

# Регистрация провайдеров по умолчанию
_default_registry = ProviderRegistry()
_default_registry.register("openai", OpenAIProvider)
_default_registry.register("anthropic", AnthropicProvider)
_default_registry.register("deepseek", DeepSeekProvider)
_default_registry.register("openrouter", OpenRouterProvider)
_default_registry.register("google", GoogleProvider)

# Алиас для совместимости с ТЗ
BaseProvider = LLMProvider

__all__ = [
    "LLMProvider",
    "BaseProvider",
    "LLMRequest",
    "LLMResponse",
    "ProviderRegistry",
    "ProviderFactory",
    "OpenAIProvider",
    "AnthropicProvider",
    "DeepSeekProvider",
    "OpenRouterProvider",
    "GoogleProvider",
]
