"""
MemoryManager — единая точка доступа к системе памяти.
Координирует Episodic, Semantic, Procedural и ArtifactKnowledgeBase.
"""

from typing import Any, Optional

from .schemas import MemoryEntry


class MemoryManager:
    """
    Менеджер памяти: объединяет доступ к различным типам памяти
    (episodic, semantic, procedural, artifact KB).
    """

    def __init__(
        self,
        episodic_memory: Any = None,
        semantic_memory: Any = None,
        procedural_memory: Any = None,
        artifact_kb: Any = None,
    ) -> None:
        """
        Инициализация MemoryManager.

        Args:
            episodic_memory: EpisodicMemory (опционально).
            semantic_memory: SemanticMemory (опционально).
            procedural_memory: ProceduralMemory (опционально).
            artifact_kb: ArtifactKnowledgeBase (опционально).
        """
        self._episodic: Any = episodic_memory
        self._semantic: Any = semantic_memory
        self._procedural: Any = procedural_memory
        self._artifact_kb: Any = artifact_kb

    @property
    def episodic(self) -> Any:
        """EpisodicMemory — ленивая инициализация."""
        if self._episodic is None:
            from .episodic import EpisodicMemory

            self._episodic = EpisodicMemory(":memory:")
        return self._episodic

    @property
    def semantic(self) -> Any:
        """SemanticMemory — ленивая инициализация."""
        if self._semantic is None:
            from .semantic import SemanticMemory

            self._semantic = SemanticMemory(
                collection_name="vagus_semantic",
                persist_directory=None,
            )
        return self._semantic

    @property
    def procedural(self) -> Any:
        """ProceduralMemory — ленивая инициализация."""
        if self._procedural is None:
            from .procedural import ProceduralMemory

            self._procedural = ProceduralMemory(":memory:")
        return self._procedural

    @property
    def artifact_kb(self) -> Any:
        """ArtifactKnowledgeBase — ленивая инициализация."""
        if self._artifact_kb is None:
            from .artifact_kb import ArtifactKnowledgeBase

            self._artifact_kb = ArtifactKnowledgeBase()
        return self._artifact_kb

    async def get_context_for_task(self, task: dict, tenant_id: str) -> dict:
        """
        Возвращает контекст для задачи из Episodic, Semantic и Procedural памяти.
        """
        task_id = task.get("task_id", "default")

        # 1. EpisodicMemory — история шагов
        history = await self.episodic.get_recent_history(
            tenant_id, task_id, limit=10
        )

        # 2. SemanticMemory — релевантные факты
        query = task.get("description") or task.get("intent", "")
        relevant_knowledge: list = []
        if query:
            try:
                relevant_knowledge = await self.semantic.search_async(
                    query, tenant_id, top_k=5
                )
            except Exception:
                relevant_knowledge = []

        # 3. ProceduralMemory — похожие планы
        intent_summary = task.get("intent_summary") or query
        similar_plans: list = []
        if intent_summary and str(intent_summary).strip():
            plan = await self.procedural.find_similar_plan(
                tenant_id, intent_summary, threshold=0.7
            )
            if plan:
                similar_plans = [plan]

        return {
            "history": history,
            "relevant_knowledge": relevant_knowledge,
            "similar_plans": similar_plans,
            "tenant_id": tenant_id,
            "task_id": task_id,
        }

    async def save_episodic_step(
        self,
        tenant_id: str,
        task_id: str,
        agent_type: str,
        action: str,
        result: dict,
        metadata: Optional[dict] = None,
    ) -> str:
        """Добавляет шаг в эпизодическую память. Делегирует в episodic.add_step_async()."""
        return await self.episodic.add_step_async(
            tenant_id, task_id, agent_type, action, result, metadata or {}
        )

    async def save_artifact(
        self,
        content: str,
        artifact_type: str,
        source_step: str,
        tenant_id: str,
        **kwargs: Any,
    ) -> str:
        """Сохранить артефакт. Делегирует в artifact_kb.write_artifact()."""
        return await self.artifact_kb.write_artifact(
            content, artifact_type, source_step, tenant_id, **kwargs
        )

    async def link_artifacts(
        self,
        source_id: str,
        target_id: str,
        tenant_id: str,
        rel_type: str = "derived_from",
    ) -> None:
        """Связать два артефакта. Делегирует в artifact_kb.link_artifacts()."""
        await self.artifact_kb.link_artifacts(
            source_id, target_id, tenant_id, rel_type
        )

    def store(self, entry: MemoryEntry) -> None:
        """
        Сохранить запись в память (заглушка — делегирует в подсистемы по metadata).

        Args:
            entry: Запись для сохранения.
        """
        # TODO: маршрутизация по entry.metadata["memory_type"]
        raise NotImplementedError("MemoryManager.store — в разработке")

    def search(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """
        Поиск по памяти (заглушка).

        Args:
            query: Поисковый запрос.
            limit: Максимум результатов.

        Returns:
            Список найденных записей.
        """
        # TODO: объединённый поиск по episodic + semantic + artifact_kb
        raise NotImplementedError("MemoryManager.search — в разработке")
