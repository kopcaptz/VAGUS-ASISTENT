"""Unit-тесты EpisodicMemory."""
import pytest

from vagus.layer2.memory import EpisodicMemory


def test_add_step_returns_step_id():
    """add_step возвращает step_id."""
    memory = EpisodicMemory()
    step_id = memory.add_step("task123", "coder", "execute_code", "result", {"lines": 10})
    assert step_id
    assert len(step_id) == 32  # uuid4().hex format


def test_get_history():
    """get_history возвращает список шагов."""
    memory = EpisodicMemory()
    memory.add_step("task123", "coder", "execute_code", "result", {"lines": 10})
    memory.add_step("task123", "researcher", "search_web", "search result")
    history = memory.get_history("task123")
    assert len(history) == 2
    assert history[0]["agent_type"] == "coder"
    assert history[0]["action"] == "execute_code"
    assert history[0]["result"] == "result"
    assert history[0]["metadata"]["lines"] == 10
    assert history[1]["agent_type"] == "researcher"


def test_get_history_empty_task():
    """get_history для несуществующей задачи возвращает []."""
    memory = EpisodicMemory()
    assert memory.get_history("nonexistent") == []


def test_get_last_step():
    """get_last_step возвращает последний шаг."""
    memory = EpisodicMemory()
    memory.add_step("task123", "coder", "execute_code", "r1")
    memory.add_step("task123", "researcher", "search_web", "r2")
    last = memory.get_last_step("task123")
    assert last is not None
    assert last["agent_type"] == "researcher"
    assert last["result"] == "r2"


def test_get_last_step_empty():
    """get_last_step для пустой задачи возвращает None."""
    memory = EpisodicMemory()
    assert memory.get_last_step("empty") is None


def test_clear_task_history():
    """clear_task_history удаляет историю задачи."""
    memory = EpisodicMemory()
    memory.add_step("task123", "coder", "execute_code", "result")
    memory.clear_task_history("task123")
    assert memory.get_history("task123") == []
    assert memory.get_last_step("task123") is None


def test_get_all_tasks():
    """get_all_tasks возвращает список task_id."""
    memory = EpisodicMemory()
    memory.add_step("t1", "coder", "execute_code", "r1")
    memory.add_step("t2", "researcher", "search_web", "r2")
    tasks = memory.get_all_tasks()
    assert set(tasks) == {"t1", "t2"}


def test_get_task_summary():
    """get_task_summary возвращает сводку."""
    memory = EpisodicMemory()
    memory.add_step("task123", "coder", "execute_code", "r1", {"lines": 5})
    memory.add_step("task123", "researcher", "search_web", "r2")
    summary = memory.get_task_summary("task123")
    assert summary["task_id"] == "task123"
    assert summary["step_count"] == 2
    assert summary["last_step"] is not None
    assert summary["last_step"]["agent_type"] == "researcher"
    assert summary["first_timestamp"] is not None
    assert summary["last_timestamp"] is not None


def test_get_task_summary_empty():
    """get_task_summary для пустой задачи."""
    memory = EpisodicMemory()
    summary = memory.get_task_summary("empty")
    assert summary["step_count"] == 0
    assert summary["last_step"] is None
    assert summary["first_timestamp"] is None


def test_step_structure():
    """Структура шага содержит все поля."""
    memory = EpisodicMemory()
    step_id = memory.add_step("t1", "analyst", "analyze_data", {"key": "value"})
    history = memory.get_history("t1")
    step = history[0]
    assert "step_id" in step
    assert step["step_id"] == step_id
    assert "timestamp" in step
    assert "agent_type" in step
    assert step["agent_type"] == "analyst"
    assert "action" in step
    assert "result" in step
    assert "metadata" in step
    assert isinstance(step["metadata"], dict)
