"""
Провайдер Google Gemini API (опционально).
"""

from typing import AsyncGenerator, Dict, Any, Optional
from .base_provider import LLMProvider

PRICING = {
    "gemini-pro": (0.50, 1.50),
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
}


def _get_pricing(model: str) -> tuple:
    for prefix, prices in PRICING.items():
        if prefix in model:
            return prices
    return (0.50, 1.50)


try:
    from google import genai
    from google.genai import types as genai_types
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False


class GoogleProvider(LLMProvider):
    """Провайдер Google Gemini API."""

    def __init__(
        self,
        name: str = "google",
        model: str = "gemini-1.5-flash",
        api_key: str = "",
        timeout: int = 30,
        **kwargs,
    ):
        super().__init__(name=name, model=model, api_key=api_key, timeout=timeout, **kwargs)
        if GOOGLE_AVAILABLE:
            self._client = genai.Client(api_key=api_key)
        else:
            self._client = None

    async def request(
        self,
        prompt: str,
        stream: bool = False,
        **kwargs,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if not GOOGLE_AVAILABLE:
            raise RuntimeError("google-genai not installed. pip install google-genai")
        model_name = kwargs.get("model") or self.model
        response = self._client.models.generate_content(model=model_name, contents=prompt)
        yield {"content": response.text or "", "done": True}

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        inp, out = _get_pricing(self.model)
        return (prompt_tokens * inp / 1e6) + (completion_tokens * out / 1e6)
