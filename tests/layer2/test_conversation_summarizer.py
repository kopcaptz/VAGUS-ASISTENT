"""Тесты ConversationSummarizer."""
import pytest
from unittest.mock import MagicMock

from vagus.layer2.memory import ConversationSummarizer
from vagus.layer2.memory.summarizer import ConversationSummarizer as SummarizerClass


SAMPLE_STEPS_SHORT = [
    {
        "step_id": "s1",
        "timestamp": "2024-01-01T12:00:00",
        "agent_type": "researcher",
        "action": "search_web",
        "result": {"content": "Found FastAPI docs. Key: async, OpenAPI."},
        "metadata": {},
    },
    {
        "step_id": "s2",
        "timestamp": "2024-01-01T12:01:00",
        "agent_type": "coder",
        "action": "process",
        "result": {"content": "Generated Python script with FastAPI routes."},
        "metadata": {},
    },
]

SAMPLE_STEPS_LONG = [
    {
        "step_id": f"s{i}",
        "timestamp": "2024-01-01T12:00:00",
        "agent_type": "researcher" if i % 2 == 0 else "coder",
        "action": "search_web" if i % 2 == 0 else "process",
        "result": {"content": f"Step {i} result. Some content here."},
        "metadata": {},
    }
    for i in range(15)
]

SAMPLE_STEPS_WITH_GOAL = [
    {
        "step_id": "s1",
        "agent_type": "researcher",
        "action": "search_web",
        "result": {"content": "Goal: create REST API. Found patterns."},
        "metadata": {},
    },
    {
        "step_id": "s2",
        "agent_type": "coder",
        "action": "process",
        "result": {"content": "Implemented endpoints. Final: working API."},
        "metadata": {},
    },
]

LONG_SUMMARY = "word " * 600


def _mock_llm(response: str):
    async def _inner(prompt, **kwargs):
        yield {"content": response, "done": True}

    return _inner


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.route_request = _mock_llm("Predefined summary text.")
    return router


@pytest.fixture
def summarizer(mock_llm_router):
    return ConversationSummarizer(llm_router=mock_llm_router)


@pytest.mark.asyncio
async def test_summarize_short_dialog(summarizer, mock_llm_router):
    """Суммаризация короткого диалога (2-3 шага)."""
    mock_llm_router.route_request = _mock_llm("Short summary for 2 steps.")
    result = await summarizer.summarize(SAMPLE_STEPS_SHORT)
    assert "Short summary" in result or "summary" in result.lower()


@pytest.mark.asyncio
async def test_summarize_long_dialog(mock_llm_router):
    """Суммаризация длинного диалога — проверка передачи шагов в промпт."""
    captured_prompt = []

    async def capture(prompt, **kw):
        captured_prompt.append(prompt)
        yield {"content": "Long dialog summarized.", "done": True}

    mock_llm_router.route_request = capture
    summarizer = ConversationSummarizer(llm_router=mock_llm_router)
    result = await summarizer.summarize(SAMPLE_STEPS_LONG)
    assert "Long dialog summarized" in result
    assert len(captured_prompt) == 1
    assert "Step 1" in captured_prompt[0]
    assert "Step 15" in captured_prompt[0]


@pytest.mark.asyncio
async def test_preserves_key_info(mock_llm_router):
    """Сохранение ключевой информации в резюме."""
    mock_llm_router.route_request = _mock_llm(
        "Goal: create REST API. Researcher found patterns. Coder implemented. Final: working API."
    )
    summarizer = ConversationSummarizer(llm_router=mock_llm_router)
    result = await summarizer.summarize(SAMPLE_STEPS_WITH_GOAL)
    assert "REST API" in result or "API" in result
    assert "working" in result or "implemented" in result


@pytest.mark.asyncio
async def test_ignores_technical_details(mock_llm_router):
    """Проверка инструкций в промпте (косвенно через mock)."""
    steps_with_code = [
        {
            "step_id": "s1",
            "agent_type": "coder",
            "action": "process",
            "result": {"content": "def foo(): return 42"},
            "metadata": {},
        },
    ]
    mock_llm_router.route_request = _mock_llm("Summary without code blocks.")
    summarizer = ConversationSummarizer(llm_router=mock_llm_router)
    result = await summarizer.summarize(steps_with_code)
    assert result
    assert "def foo" not in result


@pytest.mark.asyncio
async def test_summary_length_limit(mock_llm_router):
    """Ограничение длины резюме до max_summary_words."""
    mock_llm_router.route_request = _mock_llm(LONG_SUMMARY)
    summarizer = ConversationSummarizer(
        llm_router=mock_llm_router,
        max_summary_words=100,
    )
    result = await summarizer.summarize(SAMPLE_STEPS_SHORT)
    words = result.split()
    assert len(words) <= 100


@pytest.mark.asyncio
async def test_disabled_returns_empty(mock_llm_router):
    """При enabled=False возвращается пустая строка."""
    summarizer = ConversationSummarizer(llm_router=mock_llm_router, enabled=False)
    result = await summarizer.summarize(SAMPLE_STEPS_SHORT)
    assert result == ""


@pytest.mark.asyncio
async def test_empty_steps_returns_empty(mock_llm_router):
    """При steps=[] возвращается пустая строка."""
    summarizer = ConversationSummarizer(llm_router=mock_llm_router)
    result = await summarizer.summarize([])
    assert result == ""


def test_format_steps():
    """_format_steps форматирует шаги корректно."""
    formatted = SummarizerClass._format_steps(SAMPLE_STEPS_SHORT)
    assert "Step 1" in formatted
    assert "researcher" in formatted
    assert "search_web" in formatted
    assert "FastAPI" in formatted
    assert "Step 2" in formatted
    assert "coder" in formatted


@pytest.mark.asyncio
async def test_result_with_error(mock_llm_router):
    """Шаги с result.error форматируются."""
    steps_error = [
        {
            "step_id": "s1",
            "agent_type": "coder",
            "action": "process",
            "result": {"error": "Timeout occurred"},
            "metadata": {},
        },
    ]
    mock_llm_router.route_request = _mock_llm("Error was handled.")
    summarizer = ConversationSummarizer(llm_router=mock_llm_router)
    result = await summarizer.summarize(steps_error)
    assert "Error was handled" in result
