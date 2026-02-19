"""
EpisodicMemory — хранение истории выполнения задач (краткосрочная память).
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class EpisodicMemory:
    """
    In-memory хранилище истории выполнения задач.
    Dict[task_id, List[step]].
    """

    def __init__(self) -> None:
        self._storage: Dict[str, List[Dict[str, Any]]] = {}

    def add_step(
        self,
        task_id: str,
        agent_type: str,
        action: str,
        result: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Добавляет шаг в историю задачи.

        Args:
            task_id: Идентификатор задачи
            agent_type: Тип агента (researcher|coder|analyst)
            action: Действие (search_web|execute_code|analyze_data)
            result: Результат выполнения
            metadata: Дополнительные данные

        Returns:
            step_id — уникальный идентификатор шага
        """
        step_id = str(uuid.uuid4())
        step: Dict[str, Any] = {
            "step_id": step_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_type": agent_type,
            "action": action,
            "result": result,
            "metadata": metadata or {},
        }
        if task_id not in self._storage:
            self._storage[task_id] = []
        self._storage[task_id].append(step)
        return step_id

    def get_history(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Возвращает список всех шагов задачи в порядке добавления.

        Returns:
            Список шагов или пустой список, если задача не найдена
        """
        return list(self._storage.get(task_id, []))

    def get_last_step(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Возвращает последний шаг задачи или None.

        Returns:
            Последний шаг или None
        """
        steps = self._storage.get(task_id, [])
        return steps[-1] if steps else None

    def clear_task_history(self, task_id: str) -> None:
        """Удаляет всю историю шагов для задачи."""
        if task_id in self._storage:
            del self._storage[task_id]

    def get_all_tasks(self) -> List[str]:
        """Возвращает список всех task_id с непустой историей."""
        return list(self._storage.keys())

    def get_task_summary(self, task_id: str) -> Dict[str, Any]:
        """
        Возвращает сводку по задаче.

        Returns:
            Dict с step_count, last_step, first_timestamp, last_timestamp
        """
        steps = self._storage.get(task_id, [])
        if not steps:
            return {
                "task_id": task_id,
                "step_count": 0,
                "last_step": None,
                "first_timestamp": None,
                "last_timestamp": None,
            }
        first = steps[0]
        last = steps[-1]
        return {
            "task_id": task_id,
            "step_count": len(steps),
            "last_step": last,
            "first_timestamp": first.get("timestamp"),
            "last_timestamp": last.get("timestamp"),
        }


__all__ = ["EpisodicMemory"]
