"""Unit-тесты многошаговых задач (execute_multi_step_task)."""
import pytest
from unittest.mock import MagicMock

from vagus.layer2 import (
    AnalystAgent,
    CoderAgent,
    CommunicationLayer,
    EpisodicMemory,
    ResearcherAgent,
    SkillSystem,
    TaskOrchestrator,
)


async def _mock_llm_code(prompt: str, **kwargs):
    yield {"content": "```python\nresult = sum([1, 2, 3])\n```", "done": True}


async def _mock_llm_research(prompt: str, **kwargs):
    yield {"content": "Результаты поиска: Python популярен.", "done": True}


async def _mock_llm_analysis(prompt: str, **kwargs):
    yield {"content": "Анализ: сумма=6, среднее=2.0.", "done": True}


def _make_llm_router(content: str):
    async def stream(prompt, **kwargs):
        yield {"content": content, "done": True}
    router = MagicMock()
    router.route_request = stream
    return router


@pytest.fixture
def multi_step_orchestrator():
    """Оркестратор с Researcher, Coder, Analyst и EpisodicMemory."""
    def route_fn(prompt, **kw):
        if "код" in prompt.lower() or "скрипт" in prompt.lower():
            return _mock_llm_code(prompt, **kw)
        if "поиск" in prompt.lower() or "найди" in prompt.lower():
            return _mock_llm_research(prompt, **kw)
        return _mock_llm_analysis(prompt, **kw)

    router = MagicMock()
    router.route_request = route_fn

    communication = CommunicationLayer()
    memory = EpisodicMemory()
    skill_system = SkillSystem()
    orchestrator = TaskOrchestrator(communication=communication, memory=memory)
    orchestrator.register_agent(ResearcherAgent(llm_router=router, skill_system=skill_system))
    orchestrator.register_agent(CoderAgent(llm_router=router, skill_system=skill_system))
    orchestrator.register_agent(AnalystAgent(llm_router=router))
    return orchestrator, memory


@pytest.mark.asyncio
async def test_execute_multi_step_task_success(multi_step_orchestrator):
    """Многошаговая задача: code -> analysis."""
    orchestrator, memory = multi_step_orchestrator

    steps = [
        {"type": "code", "prompt": "Напиши код для суммы [1, 2, 3]"},
        {"type": "analysis", "prompt": "Проанализируй результат предыдущего шага"},
    ]

    result = await orchestrator.execute_multi_step_task("multi-1", steps)

    assert "error" not in result or result.get("error") is None
    assert "steps_results" in result
    assert len(result["steps_results"]) == 2
    assert result["step_count"] == 2


@pytest.mark.asyncio
async def test_execute_multi_step_task_memory(multi_step_orchestrator):
    """Проверка записи каждого шага в EpisodicMemory."""
    orchestrator, memory = multi_step_orchestrator

    steps = [
        {"type": "code", "prompt": "Сумма чисел"},
        {"type": "analysis", "prompt": "Анализ"},
    ]
    await orchestrator.execute_multi_step_task("multi-2", steps)

    history = memory.get_history("multi-2")
    assert len(history) == 2
    assert history[0]["agent_type"] == "coder"
    assert history[1]["agent_type"] == "analyst"


@pytest.mark.asyncio
async def test_execute_multi_step_task_context_aggregation(multi_step_orchestrator):
    """Контекст предыдущих шагов передаётся следующим."""
    orchestrator, _ = multi_step_orchestrator

    steps = [
        {"type": "research", "prompt": "Найди информацию о Python"},
        {"type": "analysis", "prompt": "Сделай выводы на основе поиска"},
    ]

    result = await orchestrator.execute_multi_step_task("multi-3", steps)

    assert "context" in result
    assert "previous_steps" in result["context"]
    assert len(result["context"]["previous_steps"]) == 2


@pytest.mark.asyncio
async def test_execute_multi_step_task_empty_steps():
    """Пустой список шагов возвращает error."""
    communication = CommunicationLayer()
    memory = EpisodicMemory()
    orchestrator = TaskOrchestrator(communication=communication, memory=memory)

    result = await orchestrator.execute_multi_step_task("empty", [])

    assert "error" in result
    assert result["error"] == "Empty steps"
    assert result.get("steps_results") == []
