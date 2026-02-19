"""Unit-тесты ResearcherAgent и E2E сценарий."""
import pytest
from unittest.mock import MagicMock

from vagus.layer2.agents import ResearcherAgent
from vagus.layer2 import (
    SkillSystem,
    create_orchestrator_with_researcher,
)


async def _mock_llm_stream(prompt: str, **kwargs):
    """Имитация стрима LLMRouter — один чанк с done=True."""
    yield {"content": "Python — интерпретируемый язык программирования.", "done": True}


@pytest.fixture
def mock_llm_router():
    """Мок LLMRouter без реальных API-вызовов."""
    router = MagicMock()
    router.route_request = _mock_llm_stream  # async generator
    return router


@pytest.fixture
def researcher_agent(mock_llm_router):
    return ResearcherAgent(llm_router=mock_llm_router, skill_system=SkillSystem())


@pytest.mark.asyncio
async def test_researcher_can_handle_research(researcher_agent):
    """ResearcherAgent обрабатывает тип research."""
    assert researcher_agent.can_handle("research") is True
    assert researcher_agent.can_handle("search") is True
    assert researcher_agent.can_handle("find") is True
    assert researcher_agent.can_handle("default") is True


@pytest.mark.asyncio
async def test_researcher_can_handle_cyrillic(researcher_agent):
    """ResearcherAgent обрабатывает типы на кириллице."""
    assert researcher_agent.can_handle("найди") is True


@pytest.mark.asyncio
async def test_researcher_process_returns_content(researcher_agent):
    """process возвращает content и metadata."""
    task = {"prompt": "Найди информацию о Python", "task_type": "research"}
    result = await researcher_agent.process(task)
    assert "content" in result
    assert len(result["content"]) > 0
    assert "metadata" in result
    assert result["metadata"].get("agent") == "researcher"
    assert "search_raw" in result


@pytest.mark.asyncio
async def test_researcher_process_empty_prompt(researcher_agent):
    """Пустой prompt возвращает error."""
    task = {"prompt": "", "task_type": "research"}
    result = await researcher_agent.process(task)
    assert result.get("error") == "Empty prompt"
    assert result.get("content") == ""


@pytest.mark.asyncio
async def test_researcher_uses_search_web(researcher_agent):
    """ResearcherAgent использует search_web — search_raw содержит результат заглушки."""
    task = {"prompt": "Что такое Python?", "task_type": "research"}
    result = await researcher_agent.process(task)
    assert "search_raw" in result
    assert "Python" in str(result["search_raw"]) or "Python" in result["content"]


@pytest.mark.asyncio
async def test_e2e_find_python_info(mock_llm_router):
    """
    E2E: Найди информацию о Python.
    Оркестратор + ResearcherAgent + SkillSystem.
    """
    orchestrator = create_orchestrator_with_researcher(mock_llm_router)
    result = await orchestrator.execute_task(
        task_id="e2e-1",
        prompt="Найди информацию о Python",
        task_type="research",
    )
    assert "error" not in result or result.get("error") is None
    assert "content" in result
    assert len(result["content"]) > 0
    assert "Python" in result["content"]
    assert "metadata" in result
    assert result["metadata"].get("agent") == "researcher"
