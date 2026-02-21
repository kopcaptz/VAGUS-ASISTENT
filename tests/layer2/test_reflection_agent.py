"""Unit и integration тесты ReflectionAgent."""

import pytest
from unittest.mock import MagicMock

from vagus.layer2 import create_orchestrator_full
from vagus.layer2.agents import ReflectionAgent


class _RouterProbe:
    def __init__(self, response_text: str):
        self.last_prompt = ""
        self._response_text = response_text

    async def route_request(self, prompt: str, **kwargs):
        self.last_prompt = prompt
        yield {"content": self._response_text, "done": True}


async def _mock_reflection_llm(prompt: str, **kwargs):
    yield {
        "content": (
            "Сохрани исходную цель задачи: Напиши функцию суммирования списка чисел.\n"
            "Улучшенный промпт: реализуй обработку пустого списка, добавь тесты и проверку типов."
        ),
        "done": True,
    }


async def _mock_reflection_llm_error(prompt: str, **kwargs):
    raise RuntimeError("LLM reflection unavailable")
    yield


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.route_request = _mock_reflection_llm
    return router


@pytest.fixture
def reflection_agent(mock_llm_router):
    return ReflectionAgent(llm_router=mock_llm_router)


@pytest.mark.asyncio
async def test_reflection_can_handle(reflection_agent):
    assert reflection_agent.can_handle("reflection") is True
    assert reflection_agent.can_handle("REFLECTION") is True
    assert reflection_agent.can_handle("evaluation") is False


@pytest.mark.asyncio
async def test_reflection_generates_refined_prompt_from_issues(reflection_agent):
    task = {
        "task_type": "reflection",
        "metadata": {
            "original_prompt": "Напиши функцию суммирования списка чисел.",
            "agent_result": {"content": "def sum_list(items): return sum(items)"},
            "evaluation_result": {
                "score": 0.45,
                "is_acceptable": False,
                "issues": ["нет edge-case для пустого списка", "нет проверок типов"],
                "suggestions": ["добавить edge-case", "добавить проверки типов"],
            },
            "agent_type": "coder",
        },
    }
    result = await reflection_agent.process(task)
    assert "error" not in result
    assert "content" in result
    assert "Улучшенный промпт" in result["content"]
    assert result["metadata"]["agent"] == "reflection"
    assert result["metadata"]["issues_count"] == 2


@pytest.mark.asyncio
async def test_reflection_keeps_original_goal(reflection_agent):
    task = {
        "task_type": "reflection",
        "metadata": {
            "original_prompt": "Собери краткий отчёт по продажам за квартал.",
            "agent_result": {"content": "Отчёт"},
            "evaluation_result": {
                "score": 0.5,
                "is_acceptable": False,
                "issues": ["не хватает структуры"],
                "suggestions": ["добавить разделы и выводы"],
            },
        },
    }
    result = await reflection_agent.process(task)
    assert "Сохрани исходную цель задачи" in result["content"]
    assert "Собери краткий отчёт по продажам за квартал." in result["content"]


@pytest.mark.asyncio
async def test_reflection_accounts_for_agent_type():
    router = _RouterProbe("Refined prompt with coder constraints.")
    agent = ReflectionAgent(llm_router=router)
    task = {
        "task_type": "reflection",
        "metadata": {
            "original_prompt": "Напиши код для сортировки.",
            "agent_result": {"content": "код"},
            "evaluation_result": {
                "score": 0.4,
                "is_acceptable": False,
                "issues": ["нет тестов"],
                "suggestions": ["добавить тесты"],
            },
            "agent_type": "coder",
        },
    }
    result = await agent.process(task)
    assert "error" not in result
    assert "coder" in router.last_prompt.lower()
    assert result["metadata"]["agent_type"] == "coder"


@pytest.mark.asyncio
async def test_reflection_error_handling_missing_metadata(reflection_agent):
    task = {
        "task_type": "reflection",
        "metadata": {
            "original_prompt": "Сделай улучшение.",
            "agent_result": {"content": "result only"},
        },
    }
    result = await reflection_agent.process(task)
    assert result.get("error") == "Missing evaluation_result for reflection"
    assert result.get("content") == ""


@pytest.mark.asyncio
async def test_reflection_error_handling_llm_failure(mock_llm_router):
    mock_llm_router.route_request = _mock_reflection_llm_error
    agent = ReflectionAgent(llm_router=mock_llm_router)
    task = {
        "task_type": "reflection",
        "metadata": {
            "original_prompt": "Оптимизируй решение.",
            "agent_result": {"content": "draft"},
            "evaluation_result": {
                "score": 0.2,
                "is_acceptable": False,
                "issues": ["слишком общий ответ"],
                "suggestions": ["конкретизировать шаги"],
            },
        },
    }
    result = await agent.process(task)
    assert "error" in result
    assert "Reflection failed" in str(result["error"])


@pytest.mark.asyncio
async def test_reflection_integration_via_orchestrator():
    router = MagicMock()
    router.route_request = _mock_reflection_llm
    orchestrator = create_orchestrator_full(router)
    result = await orchestrator.execute_task(
        task_id="reflect-e2e-1",
        prompt="Сделай рефлексию",
        task_type="reflection",
        metadata={
            "original_prompt": "Напиши функцию суммирования списка чисел.",
            "agent_result": {"content": "def sum_list(items): return sum(items)"},
            "evaluation_result": {
                "score": 0.4,
                "is_acceptable": False,
                "issues": ["нет проверок на входные данные"],
                "suggestions": ["добавь проверки и тесты"],
            },
            "agent_type": "coder",
        },
    )
    assert "error" not in result or result.get("error") is None
    assert "content" in result
    assert "Улучшенный промпт" in result["content"]
    assert result.get("metadata", {}).get("agent") == "reflection"
