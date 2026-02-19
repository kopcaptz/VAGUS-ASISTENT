"""
CoderAgent — агент для генерации и выполнения кода.
Использует SkillSystem (execute_python_code) и LLMRouter для генерации кода.
"""

import re
from typing import Any, Dict, Optional

from ..skills import SkillSystem
from .base_agent import BaseAgent


class CoderAgent(BaseAgent):
    """
    Агент-программист: генерация кода через LLM и выполнение через SkillSystem.
    """

    TASK_TYPES = ("code", "programming", "script", "python")

    def __init__(
        self,
        llm_router: Any,
        skill_system: Optional[SkillSystem] = None,
        description: str = "Агент для генерации и выполнения Python-кода",
    ):
        super().__init__(name="coder", llm_router=llm_router, description=description)
        self.skill_system = skill_system or SkillSystem()

    def can_handle(self, task_type: str) -> bool:
        """Обрабатывает задачи типа code, programming, script, python."""
        task_lower = (task_type or "").lower()
        return any(t in task_lower for t in self.TASK_TYPES) or task_type == "default"

    async def process(
        self,
        task_id_or_task: Any,
        prompt_or_context: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        1. Генерация кода через llm_router.route_request()
        2. Извлечение кода из ответа (_extract_code)
        3. Выполнение через skill_system.use_skill("execute_python_code")
        4. Возврат результата с полями: content, code, success, error

        Args:
            task_id_or_task: task_id (str) или task (Dict с prompt)
            prompt_or_context: prompt (str) при вызове process(task_id, prompt)
            context: Дополнительный контекст (при вызове через task dict)

        Returns:
            Dict с content, code, success, error

        Примеры:
            result = await agent.process("task123", "Напиши функцию сложения")
            result = await agent.process({"task_id": "x", "prompt": "..."})
        """
        if isinstance(task_id_or_task, dict):
            task = task_id_or_task
            context = context or prompt_or_context
        else:
            task = {
                "task_id": task_id_or_task,
                "prompt": prompt_or_context or "",
                **kwargs,
            }

        prompt = task.get("prompt", "").strip()
        task_id = task.get("task_id", "")

        if not prompt:
            return {
                "content": "",
                "code": "",
                "success": False,
                "error": "Empty prompt",
            }

        try:
            # 1. Генерация кода через LLMRouter
            code_prompt = self._build_code_prompt(prompt)
            llm_response = await self._call_llm(code_prompt)

            # 2. Извлечение кода из ответа
            code = self._extract_code(llm_response)
            if not code:
                return {
                    "content": llm_response,
                    "code": "",
                    "success": False,
                    "error": "Could not extract code from LLM response",
                }

            # 3. Выполнение через SkillSystem
            exec_result = await self.skill_system.use_skill("execute_python_code", code=code)

            if isinstance(exec_result, dict) and exec_result.get("status") == "error":
                return {
                    "content": llm_response,
                    "code": code,
                    "success": False,
                    "error": exec_result.get("message", "Execution failed"),
                }

            # 4. Формирование результата
            output = exec_result.get("output", {})
            content = self._format_output(output)
            return {
                "content": content,
                "code": code,
                "success": True,
                "error": None,
            }
        except Exception as e:
            self.logger.exception(f"CoderAgent failed: {e}")
            return {
                "content": "",
                "code": "",
                "success": False,
                "error": str(e),
            }

    def _extract_code(self, text: str) -> str:
        """
        Извлекает Python-код из ответа LLM.
        Поддерживает блоки ```python ... ``` и ``` ... ```.
        """
        if not text or not isinstance(text, str):
            return ""

        # Сначала ищем блок ```python ... ```
        match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Если нет блока с backticks — ищем от def/class/import до конца логического блока
        for pattern in (
            r"(def\s+\w+.*?(?=\n\n|\Z))",
            r"(class\s+\w+.*?(?=\n\n|\Z))",
            r"(import\s+.*?(?=\n\n|\Z))",
            r"^([a-zA-Z_][a-zA-Z0-9_]*\s*=.*?(?=\n\n|\Z))",
        ):
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return match.group(1).strip()

        return ""

    def _build_code_prompt(self, user_prompt: str) -> str:
        """Формирует промпт для LLM с инструкцией генерировать только код."""
        return (
            f"Запрос пользователя: {user_prompt}\n\n"
            "Сгенерируй только Python-код без пояснений. "
            "Оберни код в блок ```python ... ```. "
            "Код должен быть самодостаточным и готовым к выполнению."
        )

    async def _call_llm(self, prompt: str) -> str:
        """Вызывает LLMRouter и возвращает полный текст ответа."""
        content_parts: list[str] = []
        async for chunk in self.llm_router.route_request(prompt, stream=True):
            content_parts.append(chunk.get("content", ""))
            if chunk.get("done"):
                break
        return "".join(content_parts)

    def _format_output(self, output: Dict[str, Any]) -> str:
        """Преобразует output выполнения в читаемую строку."""
        if not output:
            return ""
        parts = []
        for key, value in output.items():
            if not key.startswith("_"):
                try:
                    repr_val = repr(value)
                    if len(repr_val) > 200:
                        repr_val = repr_val[:200] + "..."
                    parts.append(f"{key} = {repr_val}")
                except Exception:
                    parts.append(f"{key} = <{type(value).__name__}>")
        return "\n".join(parts) if parts else ""


__all__ = ["CoderAgent"]
