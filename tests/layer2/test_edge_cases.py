"""Тесты граничных случаев."""
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
from vagus.layer2.memory import EpisodicMemory as EpMem


async def _mock_llm(prompt: str, **kwargs):
    yield {"content": "```python\nx=1\n```", "done": True}


def test_episodic_add_steps_batch():
    """EpisodicMemory.add_steps_batch добавляет несколько шагов."""
    mem = EpMem()
    steps = [
        ("t1", "coder", "process", {"ok": 1}, None),
        ("t1", "analyst", "process", {"ok": 2}, {"meta": 1}),
    ]
    ids = mem.add_steps_batch(steps)
    assert len(ids) == 2
    assert len(mem.get_history("t1")) == 2


def test_semantic_embedding_cache():
    """SemanticMemory кэширует эмбеддинги запросов (повторные вызовы — тот же результат)."""
    mem = SemanticMemory()
    mem.add_embedding("t1", "текст для поиска", {})
    r1 = mem.search_similar("текст для поиска", top_k=1)
    r2 = mem.search_similar("текст для поиска", top_k=1)
    assert r1 == r2
    assert len(r1) == 1


@pytest.mark.asyncio
async def test_orchestrator_no_agents():
    """Оркестратор без агентов — error."""
    orch = TaskOrchestrator(communication=CommunicationLayer())
    result = await orch.execute_task("t1", "промпт", "default")
    assert "error" in result
    assert "No agent" in result["error"]


@pytest.mark.asyncio
async def test_execute_task_empty_prompt():
    """Пустой промпт — агент возвращает свой error."""
    router = MagicMock()
    router.route_request = _mock_llm
    orch = TaskOrchestrator(communication=CommunicationLayer())
    orch.register_agent(CoderAgent(router, SkillSystem()))

    result = await orch.execute_task("t1", "", "code")
    assert "error" in result or result.get("success") is False
