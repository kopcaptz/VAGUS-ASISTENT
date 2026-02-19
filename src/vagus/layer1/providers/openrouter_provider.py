"""
Провайдер OpenRouter (агрегатор моделей).
"""

from typing import AsyncGenerator, Dict, Any, Optional
from .base_provider import LLMProvider

# OpenRouter использует переменные цены; базовая оценка
DEFAULT_INPUT = 1.0   # $/1M
DEFAULT_OUTPUT = 3.0  # $/1M


try:
    from openai import AsyncOpenAI
    OPENROUTER_AVAILABLE = True
except ImportError:
    OPENROUTER_AVAILABLE = False


class OpenRouterProvider(LLMProvider):
    """Провайдер OpenRouter API."""

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        name: str = "openrouter",
        model: str = "openai/gpt-4o-mini",
        api_key: str = "",
        timeout: int = 30,
        **kwargs,
    ):
        super().__init__(name=name, model=model, api_key=api_key, timeout=timeout, **kwargs)
        self._client = None
        if not OPENROUTER_AVAILABLE:
            self.logger.warning("openai package required for OpenRouter")

    def _get_client(self):
        if not OPENROUTER_AVAILABLE:
            raise RuntimeError("openai package not installed")
        if self._client is not None:
            return self._client
        try:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.BASE_URL,
                timeout=self.timeout,
                http_client=self.get_shared_http_client(),
            )
        except TypeError:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.BASE_URL,
                timeout=self.timeout,
            )
        return self._client

    async def request(
        self,
        prompt: str,
        stream: bool = False,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if not OPENROUTER_AVAILABLE:
            raise RuntimeError("openai package not installed")
        client = self._get_client()
        model = kwargs.get("model") or self.model
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 1000)
        if stream:
            stream_resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            async for chunk in stream_resp:
                delta = chunk.choices[0].delta if chunk.choices else None
                content = delta.content if delta and delta.content else ""
                if content:
                    yield {"content": content, "done": False}
            yield {"content": "", "done": True}
        else:
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content if resp.choices else ""
            yield {"content": content or "", "done": True}

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens * DEFAULT_INPUT / 1e6) + (completion_tokens * DEFAULT_OUTPUT / 1e6)
