"""
ResearcherAgent — агент для поиска информации.
Использует SkillSystem (search_web) и LLMRouter для синтеза ответа.
"""

import re
from typing import Any, Optional

from ..skills import SkillSystem
from ..types import AgentContext, AgentResult, AgentTask
from .base_agent import BaseAgent
from .protocols import LLMRouterProtocol


class ResearcherAgent(BaseAgent):
    """
    Агент-исследователь: поиск информации в интернете и синтез ответа.
    """

    TASK_TYPES = ("research", "search", "find", "узнай", "найди")

    def __init__(
        self,
        llm_router: LLMRouterProtocol,
        skill_system: Optional[SkillSystem] = None,
        description: str = "Агент для поиска и анализа информации",
    ):
        super().__init__(name="researcher", llm_router=llm_router, description=description)
        self.skill_system = skill_system or SkillSystem()

    def can_handle(self, task_type: str) -> bool:
        """Обрабатывает задачи типа research, search, find и похожие."""
        task_lower = (task_type or "").lower()
        return any(t in task_lower for t in self.TASK_TYPES) or task_type == "default"

    async def process(
        self,
        task: AgentTask,
        context: Optional[AgentContext] = None,
    ) -> AgentResult:
        """
        1. Вызывает search_web с запросом из prompt
        2. Передаёт результаты в LLM для синтеза ответа
        3. Возвращает структурированный результат
        """
        prompt = task.get("prompt", "").strip()
        if not prompt:
            return {"content": "", "error": "Empty prompt", "metadata": {}}

        # Short conversational prompts should not depend on web-search results.
        if self._is_small_talk(prompt):
            content = await self._call_llm(self._build_chat_prompt(prompt))
            return {
                "content": content,
                "metadata": {"agent": "researcher", "mode": "chat"},
            }

        # 1. Поиск через SkillSystem
        search_result = await self.skill_system.use_skill("search_web", query=prompt)
        if isinstance(search_result, dict) and "error" in search_result:
            return {
                "content": "",
                "error": search_result["error"],
                "metadata": {"skill": "search_web"},
            }

        # 2. Синтез через LLMRouter
        llm_prompt = self._build_synthesis_prompt(prompt, str(search_result))
        content = await self._call_llm(llm_prompt)

        return {
            "content": content,
            "search_raw": search_result,
            "metadata": {"agent": "researcher", "skill_used": "search_web"},
        }

    def _build_synthesis_prompt(self, query: str, search_results: str) -> str:
        """Формирует промпт для LLM на основе запроса и результатов поиска."""
        return (
            f"Пользователь спросил: «{query}»\n\n"
            f"Результаты поиска:\n{search_results}\n\n"
            "Сформируй краткий и полезный ответ для пользователя. "
            "Используй результаты поиска как дополнительный контекст, "
            "но если они неполные или шумные — ответь по общим знаниям без выдумывания фактов."
        )

    async def _call_llm(self, prompt: str) -> str:
        """Вызывает LLMRouter и возвращает полный текст ответа."""
        content_parts: list[str] = []
        async for chunk in self.llm_router.route_request(prompt, stream=True):
            content_parts.append(chunk.get("content", ""))
            if chunk.get("done"):
                break
        return "".join(content_parts)

    def _is_small_talk(self, prompt: str) -> bool:
        normalized = " ".join(prompt.lower().split())
        if not normalized:
            return False
        patterns = (
            r"^(привет|здравствуй|здравствуйте|хай|hello|hi)\b",
            r"как дела\??$",
            r"кто ты\??$",
            r"что умеешь\??$",
            r"чем можешь помочь\??$",
        )
        return any(re.search(pattern, normalized) for pattern in patterns)

    def _build_chat_prompt(self, user_message: str) -> str:
        return (
            "Ты дружелюбный русскоязычный AI-ассистент. "
            "Это короткий диалоговый запрос пользователя, ответь естественно и по делу, "
            "без фраз про отсутствие данных.\n\n"
            f"Сообщение пользователя: {user_message}"
        )
