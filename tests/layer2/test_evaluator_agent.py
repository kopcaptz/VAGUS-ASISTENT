"""Unit-тесты EvaluatorAgent."""

import pytest
from unittest.mock import MagicMock

from vagus.layer2.agents import EvaluatorAgent


async def _mock_llm_good(prompt: str, **kwargs):
    yield {
        "content": (
            '{"score": 0.91, "issues": ["minor formatting"], '
            '"suggestions": ["add brief summary"]}'
        ),
        "done": True,
    }


async def _mock_llm_bad(prompt: str, **kwargs):
    yield {
        "content": (
            '{"score": 0.31, "issues": ["inaccurate facts", "missing steps"], '
            '"suggestions": ["verify facts", "add complete answer"]}'
        ),
        "done": True,
    }


async def _mock_llm_invalid_json(prompt: str, **kwargs):
    yield {"content": "not a json response", "done": True}


async def _mock_llm_raise(prompt: str, **kwargs):
    raise RuntimeError("LLM unavailable")
    yield


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.route_request = _mock_llm_good
    return router


@pytest.fixture
def evaluator_agent(mock_llm_router):
    return EvaluatorAgent(llm_router=mock_llm_router)


@pytest.mark.asyncio
async def test_evaluator_can_handle_evaluation(evaluator_agent):
    assert evaluator_agent.can_handle("evaluation") is True
    assert evaluator_agent.can_handle("EVALUATION") is True
    assert evaluator_agent.can_handle("analysis") is False


@pytest.mark.asyncio
async def test_evaluator_good_result_is_acceptable(evaluator_agent):
    task = {
        "task_type": "evaluation",
        "metadata": {
            "original_prompt": "Напиши функцию сложения.",
            "agent_result": {"content": "def add(a, b): return a + b"},
        },
    }
    result = await evaluator_agent.process(task)
    assert result["score"] >= 0.7
    assert result["is_acceptable"] is True
    assert isinstance(result["issues"], list)
    assert isinstance(result["suggestions"], list)


@pytest.mark.asyncio
async def test_evaluator_bad_result_not_acceptable(evaluator_agent, mock_llm_router):
    mock_llm_router.route_request = _mock_llm_bad
    task = {
        "task_type": "evaluation",
        "metadata": {
            "original_prompt": "Подготовь аналитический отчет.",
            "agent_result": {"content": "Короткий неполный ответ"},
        },
    }
    result = await evaluator_agent.process(task)
    assert result["score"] < 0.7
    assert result["is_acceptable"] is False
    assert len(result["issues"]) >= 1


@pytest.mark.asyncio
async def test_evaluator_result_structure(evaluator_agent):
    task = {
        "task_type": "evaluation",
        "metadata": {
            "original_prompt": "Сделай ревью результата.",
            "agent_result": {"content": "Результат агента"},
        },
    }
    result = await evaluator_agent.process(task)
    assert set(result.keys()) == {"score", "is_acceptable", "issues", "suggestions"}
    assert isinstance(result["score"], float)
    assert isinstance(result["is_acceptable"], bool)
    assert isinstance(result["issues"], list)
    assert isinstance(result["suggestions"], list)


@pytest.mark.asyncio
async def test_evaluator_invalid_json_handling(evaluator_agent, mock_llm_router):
    mock_llm_router.route_request = _mock_llm_invalid_json
    task = {
        "task_type": "evaluation",
        "metadata": {
            "original_prompt": "Проверь корректность.",
            "agent_result": {"content": "Ответ"},
        },
    }
    result = await evaluator_agent.process(task)
    assert result["score"] == 0.0
    assert result["is_acceptable"] is False
    assert any("Evaluation failed" in issue for issue in result["issues"])


@pytest.mark.asyncio
async def test_evaluator_llm_error_handling(evaluator_agent, mock_llm_router):
    mock_llm_router.route_request = _mock_llm_raise
    task = {
        "task_type": "evaluation",
        "metadata": {
            "original_prompt": "Оцени качество текста.",
            "agent_result": {"content": "Ответ"},
        },
    }
    result = await evaluator_agent.process(task)
    assert result["score"] == 0.0
    assert result["is_acceptable"] is False
    assert any("Evaluation failed" in issue for issue in result["issues"])


@pytest.mark.asyncio
async def test_threshold_override_priority(mock_llm_router):
    mock_llm_router.route_request = _mock_llm_bad
    agent = EvaluatorAgent(llm_router=mock_llm_router, acceptable_threshold=0.2)
    task = {
        "task_type": "evaluation",
        "metadata": {
            "original_prompt": "Оцени результат.",
            "agent_result": {"content": "Слабый ответ"},
            "acceptable_threshold": 0.5,
        },
    }
    result = await agent.process(task)
    assert result["score"] == 0.31
    assert result["is_acceptable"] is False
