"""
Система навыков (Skill System) — регистр инструментов.
Реализация — Неделя 2 (search_web, execute_python_code, read_file).
"""

from typing import Any, Awaitable, Callable

from ...layer0.logging import get_logger


class SkillSystem:
    """
    Реестр навыков для агентов.
    Агенты вызывают навыки через use_skill(name, **kwargs).
    """

    def __init__(self) -> None:
        self.logger = get_logger("layer2.skills")
        self._skills: dict[str, Callable[..., Awaitable[Any]]] = {}
        self._register_default_skills()

    def _register_default_skills(self) -> None:
        """Регистрирует навыки по умолчанию (заглушки)."""
        self.register_skill("search_web", self._search_web)
        self.register_skill("execute_python_code", self._execute_python_code)
        self.register_skill("read_file", self._read_file)

    def register_skill(self, name: str, func: Callable[..., Awaitable[Any]]) -> None:
        """
        Регистрирует навык по имени.

        Args:
            name: Имя навыка (search_web, execute_python_code, read_file, ...)
            func: Асинхронная функция (query: str) или (**kwargs) -> Any
        """
        self._skills[name] = func
        self.logger.debug(f"Skill registered: {name}")

    async def use_skill(self, name: str, **kwargs: Any) -> Any:
        """
        Выполняет навык по имени.

        Args:
            name: Имя навыка
            **kwargs: Аргументы для навыка (query, code, path, ...)

        Returns:
            Результат выполнения или dict с полем error при ошибке
        """
        if name not in self._skills:
            return {"error": f"Skill '{name}' not found."}
        try:
            result = await self._skills[name](**kwargs)
            return result
        except Exception as e:
            self.logger.exception(f"Skill '{name}' failed: {e}")
            return {"error": f"Error executing skill '{name}': {e}"}

    def list_skills(self) -> list[str]:
        """Возвращает список зарегистрированных навыков."""
        return list(self._skills.keys())

    # --- Заглушки навыков (реализация позже) ---

    async def _search_web(self, query: str) -> str:
        """Поиск в интернете (заглушка)."""
        return f"Результаты поиска по запросу '{query}': [заглушка — интеграция с API поиска в следующих итерациях]"

    async def _execute_python_code(self, code: str) -> dict[str, Any]:
        """Выполнение Python-кода (заглушка)."""
        try:
            local_vars: dict[str, Any] = {}
            exec(code, {}, local_vars)
            return {"status": "success", "output": local_vars}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def _read_file(self, path: str) -> str:
        """Чтение файла (заглушка)."""
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {e}"


__all__ = ["SkillSystem"]
