"""
Построитель ответов (stream и non-stream).
"""

from typing import Dict, Any, AsyncGenerator, Optional
from ..providers.base_provider import LLMProvider


class ResponseBuilder:
    """Сборка стрима или обычного ответа в единый формат."""

    @staticmethod
    def build_chunk(content: str, done: bool = False, **meta) -> Dict[str, Any]:
        """Формат одного чанка для стрима."""
        return {"content": content, "done": done, **meta}

    @staticmethod
    async def collect_stream(
        gen: AsyncGenerator[Dict[str, Any], None],
    ) -> tuple[str, Dict[str, Any]]:
        """
        Собирает полный ответ из стрима.

        Returns:
            (content, metadata) где metadata содержит provider, model, tokens, etc.
        """
        parts = []
        meta: Dict[str, Any] = {}
        async for chunk in gen:
            parts.append(chunk.get("content", ""))
            if chunk.get("done"):
                meta.update({k: v for k, v in chunk.items() if k not in ("content", "done")})
        return "".join(parts), meta
