"""
Провайдер DeepSeek API (OpenAI-совместимый).
"""

from typing import AsyncGenerator, Dict, Any, Optional
from .base_provider import LLMProvider

# DeepSeek pricing per 1M tokens (input, output) - очень дешёвый
PRICING = {
    "deepseek-chat": (0.14, 0.28),
    "deepseek-coder": (0.14, 0.28),
}


def _get_pricing(model: str) -> tuple:
    for prefix, prices in PRICING.items():
        if prefix in model:
            return prices
    return (0.14, 0.28)


try:
    from openai import AsyncOpenAI
    DEEPSEEK_AVAILABLE = True
except ImportError:
    DEEPSEEK_AVAILABLE = False


class DeepSeekProvider(LLMProvider):
    """Провайдер DeepSeek (OpenAI-совместимый endpoint)."""

    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"

    def __init__(
        self,
        name: str = "deepseek",
        model: str = "deepseek-chat",
        api_key: str = "",
        timeout: int = 30,
        base_url: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(name=name, model=model, api_key=api_key, timeout=timeout, **kwargs)
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self._client = None
        if not DEEPSEEK_AVAILABLE:
            self.logger.warning("openai package required for DeepSeek. pip install openai")

    def _get_client(self):
        if not DEEPSEEK_AVAILABLE:
            raise RuntimeError("openai package not installed")
        if self._client is not None:
            return self._client
        try:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                http_client=self.get_shared_http_client(),
            )
        except TypeError:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def request(
        self,
        prompt: str,
        stream: bool = False,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Отправляет запрос к DeepSeek API."""
        if not DEEPSEEK_AVAILABLE:
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
