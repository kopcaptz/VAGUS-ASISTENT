"""E2E тесты TaskOrchestrator с CoderAgent и EpisodicMemory."""
import pytest
from unittest.mock import MagicMock

from vagus.layer2 import (
    CoderAgent,
    CommunicationLayer,
    EpisodicMemory,
    SkillSystem,
    TaskOrchestrator,
)


async def _mock_llm_stream_code(prompt: str, **kwargs):
    """Имитация LLM — возвращает код для сложения чисел."""
    yield {
        "content": "```python\ndef add_numbers(a, b):\n    return a + b\n\nresult = add_numbers(2, 3)\n```",
        "done": True,
    }


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
