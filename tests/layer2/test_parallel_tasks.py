"""Тесты параллельного выполнения и нагрузочного тестирования."""
import pytest
import asyncio
from unittest.mock import MagicMock

from vagus.layer2 import (
    CoderAgent,
    CommunicationLayer,
    EpisodicMemory,
    SemanticMemory,
    SkillSystem,
    TaskOrchestrator,
)


async def _mock_llm_code(prompt: str, **kwargs):
    yield {"content": "```python\ndef add(a, b): return a + b\n```", "done": True}


@pytest.fixture
def parallel_orchestrator():
    """Оркестратор с CoderAgent для параллельных тестов."""
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
    return orchestrator


@pytest.mark.asyncio
async def test_execute_parallel_tasks_basic(parallel_orchestrator):
    """Базовый тест: 3 задачи параллельно."""
    result = await parallel_orchestrator.execute_parallel_tasks(
        task_ids=["p1", "p2", "p3"],
        prompts=["Код 1", "Код 2", "Код 3"],
        task_types=["code", "code", "code"],
    )
    assert "results" in result
    assert len(result["results"]) == 3
    assert result["completed_count"] == 3
    assert result["total_count"] == 3
    assert result["results"]["p1"].get("success") is True


@pytest.mark.asyncio
async def test_execute_parallel_tasks_semaphore(parallel_orchestrator):
    """Ограничение параллелизма: max_concurrency=2, 5 задач."""
    result = await parallel_orchestrator.execute_parallel_tasks(
        task_ids=[f"task-{i}" for i in range(5)],
        prompts=[f"Промпт {i}" for i in range(5)],
        max_concurrency=2,
    )
    assert result["total_count"] == 5
    assert result["completed_count"] == 5
    assert len(result["results"]) == 5


@pytest.mark.asyncio
async def test_execute_parallel_tasks_length_mismatch(parallel_orchestrator):
    """Несовпадение длины task_ids и prompts — error."""
    result = await parallel_orchestrator.execute_parallel_tasks(
        task_ids=["a", "b"],
        prompts=["only one"],
    )
    assert "error" in result
    assert "length mismatch" in result["error"]
    assert result.get("completed_count", 0) == 0


@pytest.mark.asyncio
async def test_execute_parallel_tasks_load_10(parallel_orchestrator):
    """Нагрузочный тест: 10 параллельных задач."""
    n = 10
    result = await parallel_orchestrator.execute_parallel_tasks(
        task_ids=[f"load-{i}" for i in range(n)],
        prompts=[f"Напиши функцию f{i}" for i in range(n)],
        max_concurrency=5,
    )
    assert result["total_count"] == n
    assert result["completed_count"] == n
    for i in range(n):
        assert f"load-{i}" in result["results"]
        assert result["results"][f"load-{i}"].get("success") is True
