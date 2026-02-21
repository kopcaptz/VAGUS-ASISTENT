"""
MemoryConsolidationHandler — консолидация памяти после завершения задачи.
Синхронизирует Episodic -> Semantic, сохраняет успешные планы в ProceduralMemory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .episodic import EpisodicMemory
    from .procedural import ProceduralMemory
    from .semantic import SemanticMemory


class MemoryConsolidationHandler:
    """
    Обрабатывает завершение задачи: sync episodic->semantic, сохранение плана.
    """

    def __init__(
        self,
        episodic_memory: "EpisodicMemory",
        semantic_memory: "SemanticMemory",
        procedural_memory: "ProceduralMemory",
    ) -> None:
        self.episodic_memory = episodic_memory
        self.semantic_memory = semantic_memory
        self.procedural_memory = procedural_memory

    async def handle_task_completed(
        self,
        task_data: dict,
        tenant_id: str,
    ) -> None:
        """
        Консолидация памяти после завершения задачи.
        - sync_episodic_to_semantic
        - сохраняет успешный план в ProceduralMemory
        """
        task_id = task_data.get("task_id", "default")
        prompt = task_data.get("prompt", "")
        intent_summary = task_data.get("intent_summary", "")
        plan_json = task_data.get("plan_json")
        success = task_data.get("success", True)

        from .semantic import sync_episodic_to_semantic

        sync_episodic_to_semantic(
            self.episodic_memory,
            self.semantic_memory,
            task_id=task_id,
            prompt=prompt,
            tenant_id=tenant_id,
        )

        if (
            success
            and plan_json
            and self.procedural_memory.enabled
            and intent_summary
        ):
            try:
                await self.procedural_memory.save_plan(
                    tenant_id, intent_summary, plan_json, success_score=1.0
                )
            except Exception:
                pass
