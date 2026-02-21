"""E2E тесты MasterOrchestrator."""
import json
import pytest
from unittest.mock import MagicMock

from vagus.layer2 import (
    AnalystAgent,
    CoderAgent,
    IntentClassifier,
    MasterOrchestrator,
    ResearcherAgent,
    SharedBlackboard,
    SkillSystem,
    TaskPlanner,
)
from vagus.layer2.agent_registry import AgentRegistry
from vagus.layer2.intent_classifier import IntentResult


def _mock_llm(json_response: str):
    async def _inner(prompt: str, **kwargs):
        yield {"content": json_response, "done": True}

    return _inner


INTENT_RESEARCH = '{"primary_intent": "research", "sub_intents": ["search_web"], "entities": {}, "complexity": "simple", "confidence": 0.9}'
INTENT_CODE = '{"primary_intent": "code", "sub_intents": ["generate_code"], "entities": {}, "complexity": "simple", "confidence": 0.9}'

SIMPLE_PLAN = {
    "plan_id": "plan_1",
    "steps": [
        {"step_id": "s1", "agent_type": "researcher", "prompt": "Найди инфо", "depends_on": [], "artefact_key": "r1"}
    ],
    "execution_mode": "sequential",
}

TWO_STEP_PLAN = {
    "plan_id": "plan_2",
    "steps": [
        {"step_id": "s1", "agent_type": "researcher", "prompt": "Найди инфо", "depends_on": [], "artefact_key": "research"},
        {"step_id": "s2", "agent_type": "coder", "prompt": "Создай код", "depends_on": ["s1"], "artefact_key": "code"},
    ],
    "execution_mode": "sequential",
}


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.route_request = _mock_llm("dummy")
    return router


@pytest.fixture
def mock_intent_classifier(mock_llm_router):
    return IntentClassifier(llm_router=mock_llm_router)


@pytest.fixture
def mock_task_planner(mock_llm_router):
    return TaskPlanner(llm_router=mock_llm_router)


@pytest.fixture
def shared_blackboard():
    return SharedBlackboard(redis_url=None)


@pytest.fixture
def agent_registry(mock_llm_router):
    async def _mock_research(prompt, **kw):
        yield {"content": "Research result: FastAPI docs found.", "done": True}

    async def _mock_code(prompt, **kw):
        yield {"content": "```python\nprint('hello')\n```", "done": True}

    async def _mock_analysis(prompt, **kw):
        yield {"content": "Analysis: data reviewed.", "done": True}

    def route(prompt, **kw):
        if "найди" in prompt.lower() or "инфо" in prompt.lower():
            return _mock_research(prompt, **kw)
        if "код" in prompt.lower():
            return _mock_code(prompt, **kw)
        return _mock_analysis(prompt, **kw)

    router = MagicMock()
    router.route_request = route
    skill_system = SkillSystem()
    registry = AgentRegistry()
    registry.register(ResearcherAgent(llm_router=router, skill_system=skill_system))
    registry.register(CoderAgent(llm_router=router, skill_system=skill_system))
    registry.register(AnalystAgent(llm_router=router))
    return registry


@pytest.fixture
def master_orchestrator(mock_llm_router, mock_intent_classifier, mock_task_planner, shared_blackboard, agent_registry):
    return MasterOrchestrator(
        llm_router=mock_llm_router,
        intent_classifier=mock_intent_classifier,
        task_planner=mock_task_planner,
        shared_blackboard=shared_blackboard,
        agent_registry=agent_registry,
    )


@pytest.mark.asyncio
async def test_process_request_simple(master_orchestrator, mock_intent_classifier, mock_task_planner):
    mock_intent_classifier.llm_router.route_request = _mock_llm(INTENT_RESEARCH)
    mock_task_planner.llm_router.route_request = _mock_llm(json.dumps(SIMPLE_PLAN, ensure_ascii=False))

    result = await master_orchestrator.process_request("Найди документацию по FastAPI")

    assert "content" in result
    assert "Research result" in result["content"] or "FastAPI" in result["content"]
    assert "metadata" in result
    assert "plan_id" in result["metadata"]


@pytest.mark.asyncio
async def test_process_request_with_dependencies(master_orchestrator, mock_intent_classifier, mock_task_planner):
    mock_intent_classifier.llm_router.route_request = _mock_llm(INTENT_CODE)
    mock_task_planner.llm_router.route_request = _mock_llm(json.dumps(TWO_STEP_PLAN, ensure_ascii=False))

    result = await master_orchestrator.process_request("Найди инфо и создай код")

    assert "content" in result
    assert "metadata" in result
    assert "artefacts" in result["metadata"]
    assert "research" in result["metadata"]["artefacts"]
    assert "code" in result["metadata"]["artefacts"]


@pytest.mark.asyncio
async def test_process_request_blackboard_artefacts(
    shared_blackboard, agent_registry, mock_llm_router, mock_intent_classifier, mock_task_planner
):
    mock_intent_classifier.llm_router.route_request = _mock_llm(INTENT_RESEARCH)
    mock_task_planner.llm_router.route_request = _mock_llm(json.dumps(SIMPLE_PLAN, ensure_ascii=False))

    orch = MasterOrchestrator(
        llm_router=mock_llm_router,
        intent_classifier=mock_intent_classifier,
        task_planner=mock_task_planner,
        shared_blackboard=shared_blackboard,
        agent_registry=agent_registry,
    )
    result = await orch.process_request("Test")

    artefacts = await shared_blackboard.read_all(result["metadata"]["plan_id"])
    assert "r1" in artefacts
    assert artefacts["r1"] is not None


@pytest.mark.asyncio
async def test_process_request_intent_classification_failure(
    master_orchestrator, mock_intent_classifier, mock_task_planner
):
    async def _fail(prompt, **kw):
        raise RuntimeError("Intent service down")

    mock_intent_classifier.llm_router.route_request = _fail
    mock_task_planner.llm_router.route_request = _mock_llm(json.dumps(SIMPLE_PLAN, ensure_ascii=False))

    result = await master_orchestrator.process_request("Найди что-то")

    assert "content" in result
    assert "metadata" in result
    assert "plan_id" in result["metadata"]


@pytest.mark.asyncio
async def test_process_request_plan_failure(master_orchestrator, mock_intent_classifier, mock_task_planner):
    mock_intent_classifier.llm_router.route_request = _mock_llm(INTENT_RESEARCH)

    async def _plan_fail(intent):
        raise ValueError("Planning failed")

    master_orchestrator.task_planner.create_plan = _plan_fail

    result = await master_orchestrator.process_request("Test")

    assert "content" in result
    assert "metadata" in result


@pytest.mark.asyncio
async def test_process_request_agent_not_found(
    mock_llm_router, mock_intent_classifier, mock_task_planner, shared_blackboard
):
    registry = AgentRegistry()
    plan_with_designer = {
        "plan_id": "p1",
        "steps": [
            {"step_id": "s1", "agent_type": "designer", "prompt": "Design UI", "depends_on": [], "artefact_key": "ui"}
        ],
        "execution_mode": "sequential",
    }
    mock_intent_classifier.llm_router.route_request = _mock_llm(INTENT_CODE)
    mock_task_planner.llm_router.route_request = _mock_llm(json.dumps(plan_with_designer, ensure_ascii=False))

    orch = MasterOrchestrator(
        llm_router=mock_llm_router,
        intent_classifier=mock_intent_classifier,
        task_planner=mock_task_planner,
        shared_blackboard=shared_blackboard,
        agent_registry=registry,
    )
    result = await orch.process_request("Design something")

    artefacts = await shared_blackboard.read_all(result["metadata"]["plan_id"])
    assert "ui" in artefacts
    assert "No agent" in str(artefacts.get("ui", {}).get("error", ""))
