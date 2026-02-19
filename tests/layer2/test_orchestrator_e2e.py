"""E2E тесты TaskOrchestrator с CoderAgent, AnalystAgent, EpisodicMemory."""
import pytest
from unittest.mock import MagicMock

from vagus.layer2 import (
    CommunicationLayer,
    EpisodicMemory,
    SkillSystem,
    TaskOrchestrator,
    create_orchestrator_full,
    CoderAgent,
)


async def _mock_llm_stream_code(prompt: str, **kwargs):
    """Имитация LLM — возвращает код для сложения чисел."""
    yield {
        "content": "```python\ndef add_numbers(a, b):\n    return a + b\n\nresult = add_numbers(2, 3)\n```",
        "done": True,
    }


async def _mock_llm_analysis(prompt: str, **kwargs):
    """Имитация LLM — аналитический ответ."""
    yield {
        "content": "Анализ набора данных: среднее=50, min=10, max=90. Тренд стабильный.",
        "done": True,
    }


def _make_router_by_purpose():
    """Роутер, возвращающий разный контент по типу запроса."""
    async def route(prompt, **kw):
        if "анализ" in prompt.lower() or "проанализируй" in prompt.lower():
            async for c in _mock_llm_analysis(prompt, **kw):
                yield c
        else:
            async for c in _mock_llm_stream_code(prompt, **kw):
                yield c
    router = MagicMock()
    router.route_request = route
    return router


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.route_request = _mock_llm_stream_code
    return router


@pytest.fixture
def orchestrator_with_coder_and_memory(mock_llm_router):
    """TaskOrchestrator с CoderAgent и EpisodicMemory."""
    communication = CommunicationLayer()
    memory = EpisodicMemory()
    skill_system = SkillSystem()
    coder = CoderAgent(llm_router=mock_llm_router, skill_system=skill_system)
    orchestrator = TaskOrchestrator(
        communication=communication,
        memory=memory,
    )
    orchestrator.register_agent(coder)
    return orchestrator, memory


@pytest.mark.asyncio
async def test_e2e_coder_orchestrator_with_memory(orchestrator_with_coder_and_memory):
    """
    E2E: TaskOrchestrator + CoderAgent + EpisodicMemory.
    Выполняет задачу «Напиши скрипт для сложения чисел» и проверяет запись в память.
    """
    orchestrator, memory = orchestrator_with_coder_and_memory

    result = await orchestrator.execute_task(
        task_id="e2e-coder-1",
        prompt="Напиши скрипт для сложения чисел",
        task_type="code",
    )

    # Проверка результата
    assert "error" not in result or result.get("error") is None
    assert result.get("success") is True
    assert "code" in result
    assert "add" in result["code"].lower() or "result" in result["code"].lower()

    # Проверка истории в EpisodicMemory
    history = memory.get_history("e2e-coder-1")
    assert len(history) == 1
    step = history[0]
    assert step["agent_type"] == "coder"
    assert step["action"] == "process"
    assert step["result"]["success"] is True
    assert "add" in str(step["result"].get("code", "")).lower()

    # Сводка задачи
    summary = memory.get_task_summary("e2e-coder-1")
    assert summary["step_count"] == 1
    assert summary["task_id"] == "e2e-coder-1"


@pytest.fixture
def full_orchestrator():
    """TaskOrchestrator с Coder, Analyst и EpisodicMemory (create_orchestrator_full)."""
    router = _make_router_by_purpose()
    orch = create_orchestrator_full(router)
    return orch, orch.memory


@pytest.mark.asyncio
async def test_e2e_multi_step_task(full_orchestrator):
    """
    E2E: Многошаговая задача code -> analysis.
    Проверка execute_multi_step_task и записи в EpisodicMemory.
    """
    orchestrator, memory = full_orchestrator

    steps = [
        {"type": "code", "prompt": "Напиши скрипт для суммы [10, 20, 30]"},
        {"type": "analysis", "prompt": "Проанализируй результат выполнения кода"},
    ]

    result = await orchestrator.execute_multi_step_task("e2e-multi-1", steps)

    assert "steps_results" in result
    assert len(result["steps_results"]) == 2
    assert result["steps_results"][0].get("success") is True
    assert "content" in result["steps_results"][1]

    history = memory.get_history("e2e-multi-1")
    assert len(history) == 2
    summary = memory.get_task_summary("e2e-multi-1")
    assert summary["step_count"] == 2


@pytest.mark.asyncio
async def test_e2e_analyst_dataset_analysis(full_orchestrator):
    """
    E2E: Анализ набора данных через AnalystAgent.
    """
    orchestrator, memory = full_orchestrator

    result = await orchestrator.execute_task(
        task_id="e2e-analyst-1",
        prompt="Проанализируй данные: продажи [100, 150, 120, 180, 200] за 5 месяцев",
        task_type="analysis",
    )

    assert "error" not in result or result.get("error") is None
    assert "content" in result
    assert len(result["content"]) > 0

    history = memory.get_history("e2e-analyst-1")
    assert len(history) == 1
    assert history[0]["agent_type"] == "analyst"
