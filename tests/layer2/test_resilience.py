"""Тесты устойчивости к ошибкам и граничных случаев."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from vagus.layer2 import (
    AnalystAgent,
    CoderAgent,
    CommunicationLayer,
    EpisodicMemory,
    ResearcherAgent,
    SemanticMemory,
    SkillSystem,
    TaskOrchestrator,
)


async def _mock_llm_ok(prompt: str, **kwargs):
    yield {"content": "OK", "done": True}


async def _mock_llm_raise(prompt: str, **kwargs):
    """Async generator, который выбрасывает при первом обращении."""
    raise RuntimeError("LLM unavailable")
    yield  # unreachable, but makes it an async generator


@pytest.fixture
def orchestrator_with_agents():
    """Оркестратор со всеми агентами."""
    router = MagicMock()
    router.route_request = _mock_llm_ok

    comm = CommunicationLayer()
    mem = EpisodicMemory()
    sem = SemanticMemory()
    orch = TaskOrchestrator(communication=comm, memory=mem, semantic_memory=sem)
    orch.register_agent(ResearcherAgent(llm_router=router, skill_system=SkillSystem()))
    orch.register_agent(CoderAgent(llm_router=router, skill_system=SkillSystem()))
    orch.register_agent(AnalystAgent(llm_router=router))
    return orch, router


@pytest.mark.asyncio
async def test_execute_task_unknown_type_fallback(orchestrator_with_agents):
    """Неизвестный тип задачи — fallback на первого агента."""
    orch, _ = orchestrator_with_agents
    result = await orch.execute_task("t1", "тест", task_type="unknown_type_xyz")
    assert "error" not in result or "No agent" not in str(result.get("error", ""))


@pytest.mark.asyncio
async def test_execute_task_agent_raises(orchestrator_with_agents):
    """Агент выбрасывает исключение — запись в memory, возврат error."""
    orch, router = orchestrator_with_agents
    router.route_request = _mock_llm_raise

    result = await orch.execute_task("t1", "промпт", task_type="analysis")
    assert "error" in result
    assert "LLM unavailable" in str(result["error"])

    history = orch.memory.get_history("t1")
    assert len(history) == 1
    assert "error" in str(history[0]["result"])


@pytest.mark.asyncio
async def test_execute_multi_step_partial_failure():
    """Многошаговая задача: сбой на втором шаге."""
    router = MagicMock()
    call_count = 0

    async def failing_second(prompt, **kw):
        nonlocal call_count
        call_count += 1
        if call_count >= 2:
            raise RuntimeError("Step 2 failed")
        yield {"content": "Step 1 OK", "done": True}

    router.route_request = failing_second

    comm = CommunicationLayer()
    mem = EpisodicMemory()
    orch = TaskOrchestrator(communication=comm, memory=mem)
    orch.register_agent(AnalystAgent(llm_router=router))

    result = await orch.execute_multi_step_task("fail-task", [
        {"type": "analysis", "prompt": "Шаг 1"},
        {"type": "analysis", "prompt": "Шаг 2"},
    ])
    assert "error" in result
    assert "Step 2 failed" in result["error"]
    assert len(result["steps_results"]) == 2


@pytest.mark.asyncio
async def test_parallel_tasks_partial_errors():
    """Параллельное выполнение: одна из задач падает."""
    router = MagicMock()
    call_count = 0

    async def fail_second(prompt, **kw):
        nonlocal call_count
        call_count += 1
        if "второй" in prompt or call_count == 2:
            raise ValueError("Intentional failure")
        yield {"content": "OK", "done": True}

    router.route_request = fail_second

    comm = CommunicationLayer()
    orch = TaskOrchestrator(communication=comm)
    orch.register_agent(AnalystAgent(llm_router=router))

    result = await orch.execute_parallel_tasks(
        task_ids=["a", "b", "c"],
        prompts=["первый", "второй падает", "третий"],
    )
    assert result["total_count"] == 3
    assert result["completed_count"] < 3
    assert len(result["errors"]) > 0
