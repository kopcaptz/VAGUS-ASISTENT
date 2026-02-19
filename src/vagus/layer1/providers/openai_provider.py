"""
Провайдер OpenAI API (GPT-4o, GPT-4o-mini, o1).
"""

from typing import AsyncGenerator, Dict, Any, Optional
from .base_provider import LLMProvider

# Цены за 1M токенов (input, output) в USD
PRICING = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4": (30.00, 60.00),
    "gpt-3.5-turbo": (0.50, 1.50),
    "o1": (15.00, 60.00),
    "o1-mini": (3.00, 12.00),
}


def _get_pricing(model: str) -> tuple:
    """Возвращает (input_per_1m, output_per_1m) для модели."""
    for prefix, prices in PRICING.items():
        if model.startswith(prefix):
            return prices
    return (2.50, 10.00)  # default gpt-4o-like


try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class OpenAIProvider(LLMProvider):
    """Провайдер OpenAI API."""

    def __init__(
        self,
        name: str = "openai",
        model: str = "gpt-4o-mini",
        api_key: str = "",
        timeout: int = 30,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(name=name, model=model, api_key=api_key, timeout=timeout, **kwargs)
        self.base_url = base_url
        self._client = None
        if not OPENAI_AVAILABLE:
            self.logger.warning("openai package not installed. Install with: pip install openai")

    def _get_client(self):
        if not OPENAI_AVAILABLE:
            raise RuntimeError("openai package not installed")
        if self._client is not None:
            return self._client

        client_kwargs = {
            "api_key": self.api_key,
            "timeout": self.timeout,
            "base_url": self.base_url,
        }
        # OpenAI SDK поддерживает кастомный httpx.AsyncClient.
        # Если версия SDK не поддерживает аргумент http_client, откатываемся gracefully.
        try:
            self._client = AsyncOpenAI(
                http_client=self.get_shared_http_client(),
                **client_kwargs,
            )
        except TypeError:
            self._client = AsyncOpenAI(**client_kwargs)
        return self._client

    async def request(
        self,
        prompt: str,
        stream: bool = False,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Отправляет запрос к OpenAI API."""
        if not OPENAI_AVAILABLE:
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
        """Расчёт стоимости в USD."""
        inp, out = _get_pricing(self.model)
        return (prompt_tokens * inp / 1e6) + (completion_tokens * out / 1e6)
