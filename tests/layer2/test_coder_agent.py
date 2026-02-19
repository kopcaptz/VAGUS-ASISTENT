"""Unit-тесты CoderAgent."""
import pytest
from unittest.mock import MagicMock

from vagus.layer2.agents import CoderAgent
from vagus.layer2 import SkillSystem


async def _mock_llm_stream_code(prompt: str, **kwargs):
    """Имитация стрима LLMRouter — возвращает код в блоке ```python."""
    yield {"content": "```python\ndef add(a, b):\n    return a + b\n```", "done": True}


@pytest.fixture
def mock_llm_router():
    """Мок LLMRouter без реальных API-вызовов."""
    router = MagicMock()
    router.route_request = _mock_llm_stream_code
    return router


@pytest.fixture
def coder_agent(mock_llm_router):
    return CoderAgent(llm_router=mock_llm_router, skill_system=SkillSystem())


@pytest.mark.asyncio
async def test_coder_can_handle_code(coder_agent):
    """CoderAgent обрабатывает тип code."""
    assert coder_agent.can_handle("code") is True
    assert coder_agent.can_handle("programming") is True
    assert coder_agent.can_handle("script") is True
    assert coder_agent.can_handle("python") is True
    assert coder_agent.can_handle("default") is True


@pytest.mark.asyncio
async def test_coder_process_returns_content_code_success(coder_agent):
    """process возвращает content, code, success, error."""
    result = await coder_agent.process("task123", "Напиши функцию сложения двух чисел")
    assert "content" in result
    assert "code" in result
    assert "success" in result
    assert "error" in result
    assert result["success"] is True
    assert "def add" in result["code"]
    assert "add" in result["content"]


@pytest.mark.asyncio
async def test_coder_process_task_dict(coder_agent):
    """process принимает task dict (BaseAgent style)."""
    task = {"task_id": "t1", "prompt": "Напиши функцию сложения"}
    result = await coder_agent.process(task)
    assert result["success"] is True
    assert "add" in result["code"] or "add" in result["content"]


@pytest.mark.asyncio
async def test_coder_process_empty_prompt(coder_agent):
    """Пустой prompt возвращает error."""
    result = await coder_agent.process("t1", "")
    assert result["success"] is False
    assert result.get("error") == "Empty prompt"
    assert result["code"] == ""


def test_extract_code_from_markdown(coder_agent):
    """_extract_code извлекает код из ```python блоков."""
    text = "Вот решение:\n```python\ndef add(a, b): return a + b\n```"
    code = coder_agent._extract_code(text)
    assert "def add" in code
    assert "return a + b" in code


def test_extract_code_empty(coder_agent):
    """_extract_code возвращает пустую строку для текста без кода."""
    assert coder_agent._extract_code("No code here") == ""
    assert coder_agent._extract_code("") == ""
