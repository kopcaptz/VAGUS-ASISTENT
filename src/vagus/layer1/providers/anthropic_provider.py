"""
Провайдер Anthropic API (Claude 3.5 Sonnet, Haiku).
"""

from typing import AsyncGenerator, Dict, Any, Optional
from .base_provider import LLMProvider

# Цены за 1M токенов (input, output) в USD
PRICING = {
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-opus": (15.00, 75.00),
    "claude-3-sonnet": (3.00, 15.00),
    "claude-3-haiku": (0.25, 1.25),
}


def _get_pricing(model: str) -> tuple:
    for prefix, prices in PRICING.items():
        if model.startswith(prefix) or prefix in model:
            return prices
    return (3.00, 15.00)


try:
    from anthropic import AsyncAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class AnthropicProvider(LLMProvider):
    """Провайдер Anthropic API."""

    def __init__(
        self,
        name: str = "anthropic",
        model: str = "claude-3-5-sonnet-20241022",
        api_key: str = "",
        timeout: int = 30,
        **kwargs,
    ):
        super().__init__(name=name, model=model, api_key=api_key, timeout=timeout, **kwargs)
        self._client = None
        if not ANTHROPIC_AVAILABLE:
            self.logger.warning("anthropic package not installed. pip install anthropic")

    def _get_client(self):
        if not ANTHROPIC_AVAILABLE:
            raise RuntimeError("anthropic package not installed")
        if self._client is not None:
            return self._client
        try:
            self._client = AsyncAnthropic(
                api_key=self.api_key,
                timeout=self.timeout,
                http_client=self.get_shared_http_client(),
            )
        except TypeError:
            self._client = AsyncAnthropic(api_key=self.api_key, timeout=self.timeout)
        return self._client

    async def request(
        self,
        prompt: str,
        stream: bool = False,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Отправляет запрос к Anthropic API."""
        if not ANTHROPIC_AVAILABLE:
            raise RuntimeError("anthropic package not installed")
        client = self._get_client()
        model = kwargs.get("model") or self.model
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 1000)

        if stream:
            async with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            ) as stream_resp:
                async for text in stream_resp.text_stream:
                    yield {"content": text, "done": False}
            yield {"content": "", "done": True}
        else:
            resp = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )
            content = "".join(
                block.text for block in resp.content if hasattr(block, "text")
            )
            yield {"content": content or "", "done": True}

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Расчёт стоимости в USD."""
        inp, out = _get_pricing(self.model)
        return (prompt_tokens * inp / 1e6) + (completion_tokens * out / 1e6)
