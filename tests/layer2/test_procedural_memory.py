"""Тесты ProceduralMemory."""
import pytest
from unittest.mock import MagicMock

from vagus.layer2.memory import ProceduralMemory, intent_to_summary
from vagus.layer2.memory.procedural import _similarity
from vagus.layer2.planning import TaskPlan, TaskPlanner, TaskStep
from vagus.layer2.intent_classifier import IntentResult


SAMPLE_PLAN: TaskPlan = {
    "plan_id": "plan_test1",
    "steps": [
        TaskStep(
            step_id="s1",
            agent_type="researcher",
            prompt="Find info",
            depends_on=[],
            artefact_key="r1",
        ),
        TaskStep(
            step_id="s2",
            agent_type="coder",
            prompt="Generate code",
            depends_on=["s1"],
            artefact_key="code",
        ),
    ],
    "execution_mode": "sequential",
}


@pytest.fixture
def procedural_memory(tmp_path):
    """ProceduralMemory с временной БД."""
    db_path = str(tmp_path / "procedural.db")
    return ProceduralMemory(db_path=db_path, enabled=True)


@pytest.fixture
def procedural_memory_memory():
    """ProceduralMemory in-memory для тестов."""
    return ProceduralMemory(db_path=":memory:", enabled=True)


@pytest.mark.asyncio
async def test_save_and_get_plan(procedural_memory_memory):
    """save_plan и get_plan по id."""
    mem = procedural_memory_memory
    plan_id = await mem.save_plan(SAMPLE_PLAN, "research code generate", success_score=1.0)
    assert plan_id
    assert len(plan_id) == 32

    fetched = await mem.get_plan(plan_id)
    assert fetched is not None
    assert fetched["plan_id"] == plan_id
    assert len(fetched["steps"]) == 2
    assert fetched["steps"][0]["agent_type"] == "researcher"
    assert fetched["execution_mode"] == "sequential"

    await mem.close()


@pytest.mark.asyncio
async def test_find_similar_plan_match(procedural_memory_memory):
    """find_similar_plan возвращает план при похожем intent."""
    mem = procedural_memory_memory
    await mem.save_plan(SAMPLE_PLAN, "research code generate python", success_score=1.0)

    intent: IntentResult = {
        "primary_intent": "research",
        "sub_intents": ["code", "generate"],
        "entities": {"lang": "python"},
        "complexity": "moderate",
        "confidence": 0.9,
    }
    similar = await mem.find_similar_plan(intent, threshold=0.3)
    assert similar is not None
    assert "steps" in similar
    assert len(similar["steps"]) == 2

    await mem.close()


@pytest.mark.asyncio
async def test_find_similar_plan_no_match(procedural_memory_memory):
    """find_similar_plan возвращает None при непохожем intent."""
    mem = procedural_memory_memory
    await mem.save_plan(SAMPLE_PLAN, "research code generate", success_score=1.0)

    intent: IntentResult = {
        "primary_intent": "design",
        "sub_intents": ["ui", "ux"],
        "entities": {},
        "complexity": "simple",
        "confidence": 0.9,
    }
    similar = await mem.find_similar_plan(intent, threshold=0.7)
    assert similar is None

    await mem.close()


@pytest.mark.asyncio
async def test_find_similar_plan_threshold(procedural_memory_memory):
    """Порог threshold влияет на результат."""
    mem = procedural_memory_memory
    await mem.save_plan(SAMPLE_PLAN, "research code analysis", success_score=1.0)

    intent: IntentResult = {
        "primary_intent": "research",
        "sub_intents": ["code"],
        "entities": {},
        "complexity": "moderate",
        "confidence": 0.9,
    }
    similar_high = await mem.find_similar_plan(intent, threshold=0.99)
    similar_low = await mem.find_similar_plan(intent, threshold=0.1)

    assert similar_high is None or similar_low is not None
    assert similar_low is not None

    await mem.close()


@pytest.mark.asyncio
async def test_increment_usage_count(procedural_memory_memory):
    """increment_usage_count увеличивает usage_count."""
    mem = procedural_memory_memory
    plan_id = await mem.save_plan(SAMPLE_PLAN, "test intent", success_score=1.0)

    all_before = await mem.get_all_plans(limit=10)
    assert len(all_before) == 1
    assert all_before[0]["usage_count"] == 0

    await mem.increment_usage_count(plan_id)
    all_after = await mem.get_all_plans(limit=10)
    assert all_after[0]["usage_count"] == 1

    await mem.increment_usage_count(plan_id)
    all_after2 = await mem.get_all_plans(limit=10)
    assert all_after2[0]["usage_count"] == 2

    await mem.close()


@pytest.mark.asyncio
async def test_get_all_plans(procedural_memory_memory):
    """get_all_plans возвращает планы с limit и порядком по created_at."""
    mem = procedural_memory_memory
    await mem.save_plan(SAMPLE_PLAN, "intent_a", success_score=0.9)
    await mem.save_plan({**SAMPLE_PLAN, "plan_id": "p2"}, "intent_b", success_score=0.8)
    await mem.save_plan({**SAMPLE_PLAN, "plan_id": "p3"}, "intent_c", success_score=0.7)

    all_plans = await mem.get_all_plans(limit=100)
    assert len(all_plans) == 3
    assert all("plan_id" in p and "intent_summary" in p and "usage_count" in p for p in all_plans)

    limited = await mem.get_all_plans(limit=2)
    assert len(limited) == 2

    await mem.close()


@pytest.mark.asyncio
async def test_disabled_no_op(procedural_memory_memory):
    """При enabled=False save не сохраняет, find возвращает None."""
    mem = ProceduralMemory(db_path=":memory:", enabled=False)
    plan_id = await mem.save_plan(SAMPLE_PLAN, "test", success_score=1.0)
    assert plan_id == ""

    fetched = await mem.get_plan("any_id")
    assert fetched is None

    similar = await mem.find_similar_plan(
        {"primary_intent": "research", "sub_intents": [], "entities": {}, "complexity": "moderate", "confidence": 0.9}
    )
    assert similar is None

    all_plans = await mem.get_all_plans()
    assert all_plans == []


@pytest.mark.asyncio
async def test_task_planner_uses_similar_plan():
    """TaskPlanner с procedural_memory возвращает похожий план без вызова LLM."""
    mem = ProceduralMemory(db_path=":memory:", enabled=True)
    await mem.save_plan(SAMPLE_PLAN, "research code generate", success_score=1.0)

    async def _mock_llm(prompt, **kw):
        yield {"content": "{}", "done": True}

    router = MagicMock()
    router.route_request = _mock_llm

    planner = TaskPlanner(
        llm_router=router,
        procedural_memory=mem,
        similarity_threshold=0.3,
    )

    intent: IntentResult = {
        "primary_intent": "research",
        "sub_intents": ["code", "generate"],
        "entities": {},
        "complexity": "moderate",
        "confidence": 0.9,
    }

    plan = await planner.create_plan(intent)
    assert plan is not None
    assert "steps" in plan
    assert len(plan["steps"]) == 2
    assert plan["steps"][0]["agent_type"] == "researcher"
    assert plan["plan_id"] != SAMPLE_PLAN["plan_id"]

    all_plans = await mem.get_all_plans()
    assert all_plans[0]["usage_count"] == 1

    await mem.close()


def test_intent_to_summary():
    """intent_to_summary формирует строку из IntentResult."""
    intent: IntentResult = {
        "primary_intent": "code",
        "sub_intents": ["generate", "test"],
        "entities": {"lang": "python"},
        "complexity": "moderate",
        "confidence": 0.9,
    }
    summary = intent_to_summary(intent)
    assert "code" in summary
    assert "generate" in summary
    assert "lang=python" in summary
    assert "moderate" in summary


def test_similarity_jaccard():
    """_similarity возвращает Jaccard score."""
    assert _similarity("a b c", "a b c") == 1.0
    assert _similarity("a b", "c d") == 0.0
    assert 0 < _similarity("research code", "research generate code") < 1.0
