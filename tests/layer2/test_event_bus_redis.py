"""Тесты Event Bus: Redis Pub/Sub и in-memory fallback."""
import asyncio
import json
import pytest

from vagus.layer2.communication import (
    CHANNEL_SYSTEM,
    CHANNEL_TASK_PREFIX,
    CommunicationLayer,
    create_communication_from_config,
)
from vagus.layer2 import MasterOrchestrator, SharedBlackboard
from vagus.layer2.agent_registry import AgentRegistry
from vagus.layer2.intent_classifier import IntentClassifier
from vagus.layer2.planning import TaskPlanner


def _redis_available() -> bool:
    """Проверка доступности Redis на localhost:6379."""
    try:
        import redis
        client = redis.Redis.from_url("redis://localhost:6379/2", decode_responses=True)
        client.ping()
        return True
    except Exception:
        return False


# --- In-memory tests ---


@pytest.mark.asyncio
async def test_publish_event_in_memory_subscriber_receives():
    """publish_event в in-memory режиме доставляет событие подписчику через subscribe."""
    comm = CommunicationLayer(redis_url=None)
    received = []

    async def on_event(msg):
        received.append(msg)

    await comm.subscribe(CHANNEL_SYSTEM, on_event)
    await comm.publish_event("test.event", {"key": "value"}, task_id=None)
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0]["event"] == "test.event"
    assert received[0]["data"] == {"key": "value"}
    assert "ts" in received[0]


@pytest.mark.asyncio
async def test_publish_event_in_memory_with_task_id():
    """publish_event с task_id публикует и в system, и в task channel."""
    comm = CommunicationLayer(redis_url=None)
    system_events = []
    task_events = []

    async def on_system(msg):
        system_events.append(msg)

    async def on_task(msg):
        task_events.append(msg)

    await comm.subscribe(CHANNEL_SYSTEM, on_system)
    await comm.subscribe(f"{CHANNEL_TASK_PREFIX}task_123", on_task)

    await comm.publish_event("agent.started", {"agent": "coder"}, task_id="task_123")
    await asyncio.sleep(0.05)

    assert len(system_events) == 1
    assert system_events[0]["event"] == "agent.started"
    assert system_events[0]["task_id"] == "task_123"

    assert len(task_events) == 1
    assert task_events[0]["event"] == "agent.started"
    assert task_events[0]["task_id"] == "task_123"


@pytest.mark.asyncio
async def test_publish_event_event_bus_disabled_no_op():
    """При event_bus_enabled=False publish_event не доставляет события."""
    comm = CommunicationLayer(redis_url=None, event_bus_enabled=False)
    received = []

    async def on_event(msg):
        received.append(msg)

    await comm.subscribe(CHANNEL_SYSTEM, on_event)
    await comm.publish_event("test.event", {"x": 1}, task_id="t1")

    assert len(received) == 0


@pytest.mark.asyncio
async def test_backward_compatibility_no_args():
    """CommunicationLayer() без аргументов сохраняет API и работает как раньше."""
    comm = CommunicationLayer()
    assert hasattr(comm, "publish")
    assert hasattr(comm, "subscribe")
    assert hasattr(comm, "publish_result")
    assert hasattr(comm, "subscribe_to_result")
    assert hasattr(comm, "publish_event")

    # publish/subscribe работают
    got = []
    async def cb(m):
        got.append(m)
    await comm.subscribe("mytopic", cb)
    await comm.publish("mytopic", {"a": 1})
    await asyncio.sleep(0.05)
    assert len(got) == 1
    assert got[0] == {"a": 1}

    # publish_result/subscribe_to_result работают
    await comm.publish_result("tid1", {"result": "ok"})
    r = await comm.subscribe_to_result("tid1", timeout=2)
    assert r == {"result": "ok"}


@pytest.mark.asyncio
async def test_create_communication_from_config():
    """create_communication_from_config читает redis_url и event_bus.enabled."""
    comm = create_communication_from_config(None)
    assert isinstance(comm, CommunicationLayer)

    comm = create_communication_from_config({})
    assert isinstance(comm, CommunicationLayer)

    comm = create_communication_from_config({
        "communication": {"redis_url": None, "event_bus": {"enabled": True}},
    })
    assert isinstance(comm, CommunicationLayer)

    comm = create_communication_from_config({
        "communication": {"redis_url": None, "event_bus": {"enabled": False}},
    })
    assert isinstance(comm, CommunicationLayer)


# --- Redis tests (skip if Redis unavailable) ---


@pytest.mark.asyncio
@pytest.mark.skipif(not _redis_available(), reason="Redis not available")
async def test_publish_event_redis_pub_sub():
    """Публикация и получение событий через Redis."""
    comm = CommunicationLayer(redis_url="redis://localhost:6379/2")
    if not comm._redis_initialized:
        pytest.skip("Redis init failed")
    try:
        received = []
        async def handler(event_type, data):
            received.append((event_type, data))

        task = asyncio.create_task(
            comm.subscribe_to_events_redis(handler, channels=[CHANNEL_SYSTEM])
        )
        await asyncio.sleep(0.2)

        await comm.publish_event("redis.test", {"payload": 42}, task_id="rt1")
        await asyncio.sleep(0.3)

        assert len(received) >= 1
        ev_type, data = received[0]
        assert ev_type == "redis.test"
        assert data["data"]["payload"] == 42
        assert data["task_id"] == "rt1"
    finally:
        await comm.close()


@pytest.mark.asyncio
async def test_communication_layer_close():
    """close() не падает при in-memory и при Redis."""
    comm = CommunicationLayer(redis_url=None)
    await comm.close()

    if _redis_available():
        comm_redis = CommunicationLayer(redis_url="redis://localhost:6379/2")
        if comm_redis._redis_initialized:
            await comm_redis.close()


# --- MasterOrchestrator integration ---


@pytest.mark.asyncio
async def test_master_orchestrator_publishes_events():
    """MasterOrchestrator с event_bus публикует task.planned, agent.started, agent.finished, task.completed."""
    from unittest.mock import MagicMock

    INTENT = '{"primary_intent": "research", "sub_intents": [], "entities": {}, "complexity": "simple", "confidence": 0.9}'
    PLAN = {
        "plan_id": "plan_x",
        "steps": [
            {"step_id": "s1", "agent_type": "researcher", "prompt": "Find info", "depends_on": [], "artefact_key": "r1"}
        ],
        "execution_mode": "sequential",
    }

    async def mock_llm(prompt, **kw):
        yield {"content": "dummy", "done": True}

    def route(prompt, **kw):
        return mock_llm(prompt, **kw)

    llm = MagicMock()
    llm.route_request = route
    intent_clf = IntentClassifier(llm_router=llm)
    intent_clf.llm_router.route_request = _make_mock_llm(INTENT)
    task_planner = TaskPlanner(llm_router=llm)
    task_planner.llm_router.route_request = _make_mock_llm(json.dumps(PLAN, ensure_ascii=False))

    event_bus = CommunicationLayer(redis_url=None)
    events_log = []

    async def capture(msg):
        events_log.append((msg.get("event", ""), msg.get("task_id"), msg.get("data", {})))

    await event_bus.subscribe(CHANNEL_SYSTEM, capture)

    from vagus.layer2 import ResearcherAgent, SkillSystem
    skill_system = SkillSystem()
    async def research_llm(prompt, **kw):
        yield {"content": "Research result.", "done": True}
    r_router = MagicMock()
    r_router.route_request = research_llm
    registry = AgentRegistry()
    registry.register(ResearcherAgent(llm_router=r_router, skill_system=skill_system))

    orch = MasterOrchestrator(
        llm_router=llm,
        intent_classifier=intent_clf,
        task_planner=task_planner,
        shared_blackboard=SharedBlackboard(redis_url=None),
        agent_registry=registry,
        event_bus=event_bus,
    )

    result = await orch.process_request("Find documentation")
    await asyncio.sleep(0.1)

    assert "content" in result
    assert "metadata" in result

    event_types = [e[0] for e in events_log]
    assert "task.planned" in event_types
    assert "agent.started" in event_types
    assert "agent.finished" in event_types
    assert "task.completed" in event_types


def _make_mock_llm(response: str):
    async def inner(prompt, **kw):
        yield {"content": response, "done": True}
    return inner
