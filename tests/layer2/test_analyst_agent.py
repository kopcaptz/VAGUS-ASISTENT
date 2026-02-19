"""Unit-тесты AnalystAgent."""
import pytest
from unittest.mock import MagicMock

from vagus.layer2.agents import AnalystAgent


async def _mock_llm_stream_analysis(prompt: str, **kwargs):
    """Имитация LLM — аналитический ответ."""
    yield {
        "content": "Анализ данных: среднее значение 42.5, медиана 40. "
        "Выводы: тренд роста 15%. Рекомендация: мониторинг.",
        "done": True,
    }


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.route_request = _mock_llm_stream_analysis
    return router


@pytest.fixture
def analyst_agent(mock_llm_router):
    return AnalystAgent(llm_router=mock_llm_router)


@pytest.mark.asyncio
async def test_analyst_can_handle_analysis(analyst_agent):
    """AnalystAgent обрабатывает типы analysis, statistics, insights, report."""
    assert analyst_agent.can_handle("analysis") is True
    assert analyst_agent.can_handle("statistics") is True
    assert analyst_agent.can_handle("insights") is True
    assert analyst_agent.can_handle("report") is True
    assert analyst_agent.can_handle("default") is True


@pytest.mark.asyncio
async def test_analyst_can_handle_cyrillic(analyst_agent):
    """AnalystAgent обрабатывает типы на кириллице."""
    assert analyst_agent.can_handle("анализ") is True
    assert analyst_agent.can_handle("отчёт") is True


@pytest.mark.asyncio
async def test_analyst_process_returns_content(analyst_agent):
    """process возвращает content и metadata."""
    task = {"prompt": "Проанализируй данные: 10, 20, 30, 40, 50", "task_type": "analysis"}
    result = await analyst_agent.process(task)
    assert "content" in result
    assert len(result["content"]) > 0
    assert "metadata" in result
    assert result["metadata"].get("agent") == "analyst"


@pytest.mark.asyncio
async def test_analyst_process_empty_prompt(analyst_agent):
    """Пустой prompt возвращает error."""
    task = {"prompt": "", "task_type": "analysis"}
    result = await analyst_agent.process(task)
    assert result.get("error") == "Empty prompt"
    assert result.get("content") == ""


@pytest.mark.asyncio
async def test_analyst_process_with_context(analyst_agent):
    """process использует context предыдущих шагов."""
    task = {"prompt": "Сделай выводы на основе данных", "task_type": "insights"}
    context = {
        "previous_steps": [
            {"content": "Данные: продажи выросли на 20%"},
        ],
    }
    result = await analyst_agent.process(task, context=context)
    assert "content" in result
    assert result["metadata"]["agent"] == "analyst"
