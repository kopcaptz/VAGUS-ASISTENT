"""Тесты TaskPlanner."""
import pytest
from unittest.mock import MagicMock

from vagus.layer2.planning import (
    TaskPlanner,
    TaskPlan,
    TaskStep,
    create_task_planner,
    task_plan_to_multi_steps,
)
from vagus.layer2.intent_classifier import IntentResult


def _mock_llm(json_response: str):
    """Возвращает async generator function для route_request."""

    async def _inner(prompt: str, **kwargs):
        yield {"content": json_response, "done": True}

    return _inner


RESEARCH_PLAN = {
    "plan_id": "plan_r1",
    "steps": [
        {
            "step_id": "s1",
            "agent_type": "researcher",
            "prompt": "Найди документацию по FastAPI",
            "depends_on": [],
            "artefact_key": "research_result",
        }
    ],
    "execution_mode": "sequential",
}

CODE_PLAN = {
    "plan_id": "plan_c1",
    "steps": [
        {
            "step_id": "s1",
            "agent_type": "coder",
            "prompt": "Сгенерируй код для парсинга CSV",
            "depends_on": [],
            "artefact_key": "generated_code",
        },
        {
            "step_id": "s2",
            "agent_type": "coder",
            "prompt": "Напиши тесты для сгенерированного кода",
            "depends_on": ["s1"],
            "artefact_key": "tests",
        },
    ],
    "execution_mode": "sequential",
}

MIXED_PLAN = {
    "plan_id": "plan_m1",
    "steps": [
        {
            "step_id": "r1",
            "agent_type": "researcher",
            "prompt": "Найди информацию про FastAPI",
            "depends_on": [],
            "artefact_key": "research",
        },
        {
            "step_id": "c1",
            "agent_type": "coder",
            "prompt": "Создай пример кода на основе найденной информации",
            "depends_on": ["r1"],
            "artefact_key": "code",
        },
    ],
    "execution_mode": "mixed",
}


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.route_request = _mock_llm('{"plan_id": "p1", "steps": [], "execution_mode": "sequential"}')
    return router


@pytest.fixture
def planner(mock_llm_router):
    return TaskPlanner(llm_router=mock_llm_router)


def _intent(primary: str, sub: list, entities: dict, complexity: str) -> IntentResult:
    return IntentResult(
        primary_intent=primary,
        sub_intents=sub,
        entities=entities,
        complexity=complexity,
        confidence=0.9,
    )


@pytest.mark.asyncio
async def test_create_plan_research_intent(mock_llm_router):
    import json

    mock_llm_router.route_request = _mock_llm(json.dumps(RESEARCH_PLAN, ensure_ascii=False))
    planner = TaskPlanner(llm_router=mock_llm_router)
    intent = _intent("research", ["search_web"], {"topic": "FastAPI"}, "simple")
    result = await planner.create_plan(intent)
    assert result["plan_id"]
    assert len(result["steps"]) == 1
    assert result["steps"][0]["agent_type"] == "researcher"
    assert result["steps"][0]["prompt"]


@pytest.mark.asyncio
async def test_create_plan_code_intent(mock_llm_router):
    import json

    mock_llm_router.route_request = _mock_llm(json.dumps(CODE_PLAN, ensure_ascii=False))
    planner = TaskPlanner(llm_router=mock_llm_router)
    intent = _intent("code", ["generate_code", "test_code"], {"language": "Python"}, "moderate")
    result = await planner.create_plan(intent)
    assert len(result["steps"]) >= 2
    assert any(s["agent_type"] == "coder" for s in result["steps"])
    assert result["execution_mode"] == "sequential"


@pytest.mark.asyncio
async def test_create_plan_mixed_intent(mock_llm_router):
    import json

    mock_llm_router.route_request = _mock_llm(json.dumps(MIXED_PLAN, ensure_ascii=False))
    planner = TaskPlanner(llm_router=mock_llm_router)
    intent = _intent("mixed", ["search_web", "generate_code"], {"topic": "FastAPI"}, "moderate")
    result = await planner.create_plan(intent)
    assert len(result["steps"]) >= 2
    assert result["steps"][1]["depends_on"] == ["r1"]
    assert result["execution_mode"] == "mixed"


@pytest.mark.asyncio
async def test_create_plan_dependencies_valid(mock_llm_router):
    import json

    plan_with_deps = {
        "plan_id": "p1",
        "steps": [
            {"step_id": "a", "agent_type": "coder", "prompt": "Step A", "depends_on": [], "artefact_key": "a"},
            {"step_id": "b", "agent_type": "coder", "prompt": "Step B", "depends_on": ["a"], "artefact_key": "b"},
            {"step_id": "c", "agent_type": "coder", "prompt": "Step C", "depends_on": ["x"], "artefact_key": "c"},
        ],
        "execution_mode": "sequential",
    }
    mock_llm_router.route_request = _mock_llm(json.dumps(plan_with_deps, ensure_ascii=False))
    planner = TaskPlanner(llm_router=mock_llm_router)
    intent = _intent("code", [], {}, "moderate")
    result = await planner.create_plan(intent)
    step_c = next(s for s in result["steps"] if s["step_id"] == "c")
    assert step_c["depends_on"] == []


@pytest.mark.asyncio
async def test_create_plan_validation(mock_llm_router):
    import json

    invalid_plan = {
        "plan_id": "p1",
        "steps": [
            {
                "step_id": "s1",
                "agent_type": "unknown_agent",
                "prompt": "Do something",
                "depends_on": [],
                "artefact_key": "out",
            }
        ],
        "execution_mode": "sequential",
    }
    mock_llm_router.route_request = _mock_llm(json.dumps(invalid_plan, ensure_ascii=False))
    planner = TaskPlanner(llm_router=mock_llm_router)
    intent = _intent("code", [], {}, "simple")
    result = await planner.create_plan(intent)
    assert result["steps"][0]["agent_type"] == "coder"


@pytest.mark.asyncio
async def test_create_plan_parse_error_fallback(mock_llm_router):
    mock_llm_router.route_request = _mock_llm("not valid json {")
    planner = TaskPlanner(llm_router=mock_llm_router)
    intent = _intent("code", [], {}, "simple")
    result = await planner.create_plan(intent)
    assert result["plan_id"]
    assert len(result["steps"]) == 1
    assert result["execution_mode"] == "sequential"
    assert result["steps"][0]["agent_type"] == "coder"


@pytest.mark.asyncio
async def test_create_plan_max_steps(mock_llm_router):
    import json

    many_steps = {
        "plan_id": "p1",
        "steps": [
            {
                "step_id": f"s{i}",
                "agent_type": "coder",
                "prompt": f"Step {i}",
                "depends_on": ["s" + str(i - 1)] if i > 0 else [],
                "artefact_key": f"art{i}",
            }
            for i in range(15)
        ],
        "execution_mode": "sequential",
    }
    mock_llm_router.route_request = _mock_llm(json.dumps(many_steps, ensure_ascii=False))
    planner = TaskPlanner(llm_router=mock_llm_router, max_steps=5)
    intent = _intent("code", [], {}, "complex")
    result = await planner.create_plan(intent)
    assert len(result["steps"]) == 5


@pytest.mark.asyncio
async def test_create_plan_artefact_keys_unique(mock_llm_router):
    import json

    dup_artefacts = {
        "plan_id": "p1",
        "steps": [
            {"step_id": "s1", "agent_type": "coder", "prompt": "A", "depends_on": [], "artefact_key": "same"},
            {"step_id": "s2", "agent_type": "coder", "prompt": "B", "depends_on": ["s1"], "artefact_key": "same"},
        ],
        "execution_mode": "sequential",
    }
    mock_llm_router.route_request = _mock_llm(json.dumps(dup_artefacts, ensure_ascii=False))
    planner = TaskPlanner(llm_router=mock_llm_router)
    intent = _intent("code", [], {}, "simple")
    result = await planner.create_plan(intent)
    keys = [s["artefact_key"] for s in result["steps"]]
    assert len(keys) == len(set(keys))


@pytest.mark.asyncio
async def test_create_plan_execution_mode(mock_llm_router):
    import json

    complex_plan = {
        "plan_id": "p1",
        "steps": [
            {"step_id": "s1", "agent_type": "coder", "prompt": "A", "depends_on": [], "artefact_key": "a"},
        ],
        "execution_mode": "parallel",
    }
    mock_llm_router.route_request = _mock_llm(json.dumps(complex_plan, ensure_ascii=False))
    planner = TaskPlanner(llm_router=mock_llm_router)
    intent = _intent("code", [], {}, "complex")
    result = await planner.create_plan(intent)
    assert result["execution_mode"] == "parallel"


@pytest.mark.asyncio
async def test_task_plan_to_multi_steps():
    plan: TaskPlan = {
        "plan_id": "p1",
        "steps": [
            {"step_id": "s1", "agent_type": "coder", "prompt": "Step 1", "depends_on": [], "artefact_key": "a"},
            {"step_id": "s2", "agent_type": "analyst", "prompt": "Step 2", "depends_on": ["s1"], "artefact_key": "b"},
        ],
        "execution_mode": "sequential",
    }
    steps = task_plan_to_multi_steps(plan)
    assert len(steps) == 2
    assert steps[0]["type"] == "coder"
    assert steps[1]["type"] == "analyst"
    assert steps[0]["prompt"] == "Step 1"
    assert steps[1]["prompt"] == "Step 2"


def test_create_task_planner():
    router = MagicMock()
    planner = create_task_planner(router, {"max_steps": 5})
    assert planner.max_steps == 5
    planner2 = create_task_planner(router)
    assert planner2.max_steps == 10
