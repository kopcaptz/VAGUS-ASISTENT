"""Тесты create_master_orchestrator_full — проверка полной проводки компонентов."""
import pytest
from unittest.mock import MagicMock

from vagus.layer2 import (
    create_master_orchestrator_full,
    MasterOrchestrator,
    IntentClassifier,
    TaskPlanner,
    SharedBlackboard,
)
from vagus.layer2.communication import CommunicationLayer


def _mock_llm(content: str = "{}"):
    async def _inner(prompt: str, **kwargs):
        yield {"content": content, "done": True}

    return _inner


@pytest.fixture
def mock_llm_router():
    router = MagicMock()
    router.route_request = _mock_llm()
    return router


@pytest.fixture
def layer2_config():
    return {
        "conversation_summarizer": {
            "enabled": True,
            "max_input_steps": 50,
            "min_summary_words": 50,
            "max_summary_words": 500,
        },
        "procedural_memory": {
            "enabled": True,
            "db_path": ":memory:",
            "similarity_threshold": 0.7,
        },
        "communication": {
            "redis_url": None,
            "event_bus": {"enabled": True},
        },
        "blackboard": {"redis_url": None, "ttl_hours": 24},
        "intent_classifier": {"confidence_threshold": 0.5},
        "task_planner": {"max_steps": 10},
        "master_orchestrator": {"enable_reflexion": False, "enable_evaluator": False},
    }


def test_create_master_orchestrator_full_wires_all_components(
    mock_llm_router, layer2_config, tmp_path
):
    """Проверяет что create_master_orchestrator_full создаёт полный стек с всеми компонентами."""
    layer2_config["procedural_memory"]["db_path"] = str(tmp_path / "proc.db")
    orch = create_master_orchestrator_full(
        mock_llm_router,
        layer2_config=layer2_config,
    )
    assert isinstance(orch, MasterOrchestrator)

    assert orch.intent_classifier is not None
    assert isinstance(orch.intent_classifier, IntentClassifier)

    assert orch.task_planner is not None
    assert isinstance(orch.task_planner, TaskPlanner)

    assert orch.shared_blackboard is not None
    assert isinstance(orch.shared_blackboard, SharedBlackboard)

    assert orch.event_bus is not None
    assert isinstance(orch.event_bus, CommunicationLayer)

    assert orch.procedural_memory is not None
    assert orch.procedural_memory.enabled is True

    assert orch.conversation_summarizer is not None
    assert orch.conversation_summarizer.enabled is True

    assert orch.agent_registry is not None
    agents = orch.agent_registry.list()
    agent_names = [getattr(a, "name", str(a)) for a in agents]
    assert "researcher" in agent_names or any("research" in n.lower() for n in agent_names)
    assert "coder" in agent_names or any("coder" in n.lower() for n in agent_names)
    assert "analyst" in agent_names or any("analyst" in n.lower() for n in agent_names)
    assert "evaluator" in agent_names or any("eval" in n.lower() for n in agent_names)
    assert "reflection" in agent_names or any("reflect" in n.lower() for n in agent_names)
    assert "designer" in agent_names or any("design" in n.lower() for n in agent_names)


def test_create_master_orchestrator_full_with_empty_config(mock_llm_router):
    """Проверяет что create_master_orchestrator_full работает с пустой конфигурацией."""
    orch = create_master_orchestrator_full(mock_llm_router, layer2_config=None)
    assert isinstance(orch, MasterOrchestrator)
    assert orch.intent_classifier is not None
    assert orch.task_planner is not None
    assert orch.shared_blackboard is not None


@pytest.mark.asyncio
async def test_master_orchestrator_execute_task_api_compatible(
    mock_llm_router, layer2_config, tmp_path
):
    """Проверяет что MasterOrchestrator.execute_task совместим с API (делегирует в process_request)."""
    import json

    layer2_config["procedural_memory"]["db_path"] = str(tmp_path / "proc.db")
    orch = create_master_orchestrator_full(mock_llm_router, layer2_config=layer2_config)

    plan = {
        "plan_id": "p1",
        "steps": [
            {"step_id": "s1", "agent_type": "researcher", "prompt": "Test", "depends_on": [], "artefact_key": "r1"}
        ],
        "execution_mode": "sequential",
    }
    intent_json = '{"primary_intent": "research", "complexity": "simple", "confidence": 0.9}'
    responses = [intent_json, json.dumps(plan, ensure_ascii=False), "Research result"]
    call_idx = [0]

    async def route_multi(prompt, **kw):
        idx = min(call_idx[0], len(responses) - 1)
        call_idx[0] += 1
        async for chunk in _mock_llm(responses[idx]):
            yield chunk

    orch.intent_classifier.llm_router.route_request = route_multi
    orch.task_planner.llm_router.route_request = route_multi
    for agent in orch.agent_registry.list():
        agent.llm_router.route_request = route_multi

    result = await orch.execute_task(task_id="t1", prompt="Test prompt", task_type="code")

    assert "content" in result
    assert "metadata" in result
    assert result["metadata"].get("task_id") == "t1"
