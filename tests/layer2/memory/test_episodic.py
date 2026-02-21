"""Тесты EpisodicMemory (async API, tenant_id, get_recent_history)."""

import pytest

from vagus.layer2.memory import EpisodicMemory


@pytest.fixture
def memory():
    """EpisodicMemory с in-memory БД."""
    return EpisodicMemory(":memory:")


@pytest.mark.asyncio
async def test_add_step_async(memory):
    """add_step_async возвращает step_id (UUID), запись есть в БД с tenant_id."""
    step_id = await memory.add_step_async(
        "tenant1", "task1", "coder", "execute", {"result": "ok"}, {"k": 1}
    )
    assert step_id
    assert len(step_id) == 32
    history = await memory.get_recent_history("tenant1", "task1", limit=10)
    assert len(history) == 1
    assert history[0]["step_id"] == step_id
    assert history[0]["agent_type"] == "coder"
    assert history[0]["action"] == "execute"
    assert history[0]["result"] == {"result": "ok"}
    assert history[0]["metadata"] == {"k": 1}


@pytest.mark.asyncio
async def test_get_recent_history(memory):
    """get_recent_history возвращает последние limit шагов в DESC."""
    for i in range(5):
        await memory.add_step_async(
            "t1", "task1", "agent", f"action_{i}", {"i": i}
        )
    recent = await memory.get_recent_history("t1", "task1", limit=3)
    assert len(recent) == 3
    assert recent[0]["action"] == "action_4"
    assert recent[1]["action"] == "action_3"
    assert recent[2]["action"] == "action_2"


@pytest.mark.asyncio
async def test_get_recent_history_tenant_isolation(memory):
    """Данные разных tenant_id не смешиваются."""
    await memory.add_step_async("tenant_a", "task1", "a", "act", {})
    await memory.add_step_async("tenant_b", "task1", "b", "act", {})
    hist_a = await memory.get_recent_history("tenant_a", "task1")
    hist_b = await memory.get_recent_history("tenant_b", "task1")
    assert len(hist_a) == 1
    assert len(hist_b) == 1
    assert hist_a[0]["agent_type"] == "a"
    assert hist_b[0]["agent_type"] == "b"


@pytest.mark.asyncio
async def test_get_recent_history_empty(memory):
    """get_recent_history возвращает [] для несуществующей пары tenant/task."""
    hist = await memory.get_recent_history("t1", "nonexistent")
    assert hist == []
