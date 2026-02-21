"""Тесты ProceduralMemory (save_plan, find_similar_plan, increment_usage)."""

import json
import pytest

from vagus.layer2.memory import ProceduralMemory


@pytest.fixture
def memory():
    """ProceduralMemory с in-memory БД."""
    return ProceduralMemory(":memory:")


@pytest.mark.asyncio
async def test_save_plan_returns_uuid(memory):
    """save_plan возвращает 32-char plan_id, запись есть в БД."""
    plan_json = json.dumps({"steps": [{"agent_type": "coder", "prompt": "test"}]})
    plan_id = await memory.save_plan("tenant1", "search web find code", plan_json, success_score=0.8)
    assert plan_id
    assert len(plan_id) == 32

    found = await memory.find_similar_plan("tenant1", "search web find code", threshold=0.5)
    assert found is not None
    assert found.get("plan_id") == plan_id


@pytest.mark.asyncio
async def test_save_plan_stores_all_fields(memory):
    """save_plan сохраняет tenant_id, intent_summary, plan_json, success_score, usage_count."""
    plan_data = {"steps": [{"agent_type": "researcher", "prompt": "analyze"}]}
    plan_json = json.dumps(plan_data)
    plan_id = await memory.save_plan(
        "t1", "analyze data complex", plan_json, success_score=0.9
    )
    found = await memory.find_similar_plan("t1", "analyze data complex", threshold=0.5)
    assert found is not None
    assert found["plan_id"] == plan_id
    assert "steps" in found
    assert found["steps"][0]["agent_type"] == "researcher"

    await memory.increment_usage(plan_id, "t1")
    found2 = await memory.find_similar_plan("t1", "analyze data complex", threshold=0.5)
    assert found2 is not None
    # usage_count increased - plan still found (we don't expose usage_count in returned dict)


@pytest.mark.asyncio
async def test_find_similar_plan_exact_match(memory):
    """Точное совпадение intent_summary возвращает план."""
    plan_json = json.dumps({"steps": [{"agent_type": "coder"}]})
    await memory.save_plan("t1", "write python script", plan_json)
    result = await memory.find_similar_plan("t1", "write python script", threshold=0.7)
    assert result is not None
    assert result.get("steps") is not None


@pytest.mark.asyncio
async def test_find_similar_plan_similarity_threshold(memory):
    """Jaccard >= threshold возвращает план; ниже — None."""
    plan_json = json.dumps({"steps": [{"agent_type": "coder"}]})
    await memory.save_plan("t1", "write python script", plan_json)

    result_high = await memory.find_similar_plan(
        "t1", "write python script", threshold=0.5
    )
    assert result_high is not None

    result_exact = await memory.find_similar_plan(
        "t1", "write python script", threshold=1.0
    )
    assert result_exact is not None

    result_low = await memory.find_similar_plan(
        "t1", "completely different intent xyz", threshold=0.9
    )
    assert result_low is None


@pytest.mark.asyncio
async def test_find_similar_plan_tenant_isolation(memory):
    """Планы tenant_a не возвращаются для tenant_b."""
    plan_json = json.dumps({"steps": [{"agent_type": "coder"}]})
    await memory.save_plan("tenant_a", "same intent summary", plan_json)

    result_a = await memory.find_similar_plan(
        "tenant_a", "same intent summary", threshold=0.7
    )
    assert result_a is not None

    result_b = await memory.find_similar_plan(
        "tenant_b", "same intent summary", threshold=0.7
    )
    assert result_b is None


@pytest.mark.asyncio
async def test_find_similar_plan_best_success_score(memory):
    """При нескольких совпадениях возвращается план с max success_score."""
    plan_json_low = json.dumps({"steps": [{"agent_type": "coder"}]})
    plan_json_high = json.dumps({"steps": [{"agent_type": "researcher"}]})
    await memory.save_plan("t1", "search and analyze", plan_json_low, success_score=0.6)
    await memory.save_plan("t1", "search and analyze", plan_json_high, success_score=0.95)

    result = await memory.find_similar_plan("t1", "search and analyze", threshold=0.5)
    assert result is not None
    # Should return the one with higher success_score (0.95)
    assert result["steps"][0]["agent_type"] == "researcher"


@pytest.mark.asyncio
async def test_increment_usage(memory):
    """increment_usage увеличивает usage_count на 1."""
    plan_json = json.dumps({"steps": []})
    plan_id = await memory.save_plan("t1", "intent", plan_json)

    await memory.increment_usage(plan_id, "t1")
    await memory.increment_usage(plan_id, "t1")

    plans = await memory.get_all_plans(limit=10)
    assert len(plans) == 1
    assert plans[0]["usage_count"] == 2


@pytest.mark.asyncio
async def test_increment_usage_tenant_verify(memory):
    """increment_usage обновляет только при совпадении plan_id и tenant_id."""
    plan_json = json.dumps({"steps": []})
    plan_id = await memory.save_plan("tenant_a", "intent", plan_json)

    await memory.increment_usage(plan_id, "tenant_a")
    await memory.increment_usage(plan_id, "tenant_b")  # wrong tenant, no effect

    plans = await memory.get_all_plans(limit=10)
    assert len(plans) == 1
    assert plans[0]["usage_count"] == 1


@pytest.mark.asyncio
async def test_find_similar_plan_empty(memory):
    """find_similar_plan возвращает None когда планов нет."""
    result = await memory.find_similar_plan("t1", "any intent", threshold=0.5)
    assert result is None


@pytest.mark.asyncio
async def test_backward_compat_save_plan(memory):
    """save_plan(plan, intent_summary, success_score) — backward compat."""
    plan = {"steps": [{"agent_type": "coder", "prompt": "old api"}]}
    plan_id = await memory.save_plan(plan, "old style intent", success_score=1.0)
    assert plan_id
    assert len(plan_id) == 32

    result = await memory.find_similar_plan("default", "old style intent", threshold=0.5)
    assert result is not None
    assert result["steps"][0]["prompt"] == "old api"


@pytest.mark.asyncio
async def test_backward_compat_find_similar_plan(memory):
    """find_similar_plan(intent, threshold) — backward compat с IntentResult."""
    plan_json = json.dumps({"steps": [{"agent_type": "coder"}]})
    await memory.save_plan("default", "mixed research code moderate", plan_json)

    intent = {
        "primary_intent": "mixed",
        "sub_intents": ["research", "code"],
        "entities": {},
        "complexity": "moderate",
    }
    result = await memory.find_similar_plan(intent, threshold=0.5)
    assert result is not None
