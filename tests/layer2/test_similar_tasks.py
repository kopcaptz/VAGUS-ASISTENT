"""Тесты поиска похожих задач и интеграции с TaskOrchestrator."""
import pytest
from unittest.mock import MagicMock

from vagus.layer2 import (
    CoderAgent,
    CommunicationLayer,
    EpisodicMemory,
    SemanticMemory,
    SkillSystem,
    TaskOrchestrator,
)
from vagus.layer2.memory import sync_episodic_to_semantic


async def _mock_llm_code(prompt: str, **kwargs):
    yield {"content": "```python\ndef add(a, b): return a + b\n```", "done": True}


@pytest.fixture
def orchestrator_with_semantic():
    """Оркестратор с EpisodicMemory и SemanticMemory."""
    router = MagicMock()
    router.route_request = _mock_llm_code

    communication = CommunicationLayer()
    memory = EpisodicMemory()
    semantic = SemanticMemory()
    skill_system = SkillSystem()
    coder = CoderAgent(llm_router=router, skill_system=skill_system)

    orchestrator = TaskOrchestrator(
        communication=communication,
        memory=memory,
        semantic_memory=semantic,
    )
    orchestrator.register_agent(coder)
    return orchestrator, memory, semantic


@pytest.mark.asyncio
async def test_similar_task_context_added(orchestrator_with_semantic):
    """
    После выполнения задачи она попадает в SemanticMemory.
    Похожий запрос находит контекст.
    """
    orchestrator, memory, semantic = orchestrator_with_semantic

    # Первая задача
    await orchestrator.execute_task(
        task_id="task-1",
        prompt="Напиши функцию сложения двух чисел",
        task_type="code",
    )

    # Проверка: задача добавлена в Semantic
    similar = semantic.search_similar("функция сложения чисел", top_k=1)
    assert len(similar) >= 1
    assert similar[0]["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_sync_episodic_to_semantic():
    """sync_episodic_to_semantic переносит данные из Episodic в Semantic."""
    episodic = EpisodicMemory()
    semantic = SemanticMemory()

    episodic.add_step("t1", "coder", "process", {"content": "result", "success": True})
    emb_id = sync_episodic_to_semantic(episodic, semantic, "t1", "промпт задачи", "code")

    assert emb_id is not None
    results = semantic.search_similar("промпт задачи", top_k=1)
    assert len(results) == 1
    assert results[0]["metadata"]["result"]["success"] is True


@pytest.mark.asyncio
async def test_sync_episodic_empty_returns_none():
    """sync_episodic_to_semantic для задачи без шагов возвращает None."""
    episodic = EpisodicMemory()
    semantic = SemanticMemory()
    result = sync_episodic_to_semantic(episodic, semantic, "empty", "промпт", "code")
    assert result is None
