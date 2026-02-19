"""Stage 4 resilience tests: timeouts and graceful degradation."""

import asyncio

import pytest

from vagus.layer2.communication import CommunicationLayer
from vagus.layer2.dead_letter_queue import DeadLetterQueueStorage
from vagus.layer2.orchestrator import TaskOrchestrator
from vagus.layer2.agents.base_agent import BaseAgent


class _SlowAnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="analyst", llm_router=None, description="slow")

    def can_handle(self, task_type: str) -> bool:
        return "analysis" in (task_type or "").lower()

    async def process(self, task, context=None):
        await asyncio.sleep(0.05)
        return {"content": "done"}


class _UnavailableResearcherAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="researcher", llm_router=None, description="offline")
        self.process_called = False

    def can_handle(self, task_type: str) -> bool:
        return "research" in (task_type or "").lower()

    def is_available(self) -> bool:
        return False

    async def process(self, task, context=None):
        self.process_called = True
        return {"content": "should-not-run"}


class _UnavailableCoderAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="coder", llm_router=None, description="offline")
        self.process_called = False

    def can_handle(self, task_type: str) -> bool:
        return "code" in (task_type or "").lower()

    def is_available(self) -> bool:
        return False

    async def process(self, task, context=None):
        self.process_called = True
        return {"content": "should-not-run"}


class _UnavailableAnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="analyst", llm_router=None, description="offline")
        self.process_called = False

    def can_handle(self, task_type: str) -> bool:
        return "analysis" in (task_type or "").lower()

    def is_available(self) -> bool:
        return False

    async def process(self, task, context=None):
        self.process_called = True
        return {"content": "should-not-run"}


@pytest.mark.asyncio
async def test_task_timeout_records_dead_letter_queue_entry(tmp_path):
    dlq = DeadLetterQueueStorage(str(tmp_path / "dlq-timeout.db"))
    orch = TaskOrchestrator(
        communication=CommunicationLayer(),
        dead_letter_queue=dlq,
        task_timeouts={"analyst": 0.01},
    )
    orch.register_agent(_SlowAnalystAgent())

    result = await orch.execute_task("timeout-task", "Сделай анализ", task_type="analysis")
    assert "error" in result
    assert "timed out" in result["error"].lower()

    entries = dlq.list_entries(limit=5)
    assert entries
    assert entries[0]["task_id"] == "timeout-task"
    assert "timed out" in entries[0]["error_message"].lower()


@pytest.mark.asyncio
async def test_graceful_degradation_researcher_unavailable():
    agent = _UnavailableResearcherAgent()
    orch = TaskOrchestrator(communication=CommunicationLayer())
    orch.register_agent(agent)

    result = await orch.execute_task("deg-r", "Найди информацию о Python", task_type="research")
    assert result["metadata"]["degraded"] is True
    assert result["metadata"]["fallback_strategy"] == "web_search"
    assert agent.process_called is False


@pytest.mark.asyncio
async def test_graceful_degradation_coder_unavailable():
    agent = _UnavailableCoderAgent()
    orch = TaskOrchestrator(communication=CommunicationLayer())
    orch.register_agent(agent)

    result = await orch.execute_task("deg-c", "Напиши код сортировки", task_type="code")
    assert result["metadata"]["degraded"] is True
    assert result["metadata"]["fallback_strategy"] == "pseudocode"
    assert "PSEUDOCODE" in result["content"]
    assert agent.process_called is False


@pytest.mark.asyncio
async def test_graceful_degradation_analyst_unavailable():
    agent = _UnavailableAnalystAgent()
    orch = TaskOrchestrator(communication=CommunicationLayer())
    orch.register_agent(agent)

    result = await orch.execute_task("deg-a", "Сделай анализ продаж", task_type="analysis")
    assert result["metadata"]["degraded"] is True
    assert result["metadata"]["fallback_strategy"] == "simple_summary"
    assert "Simple summary" in result["content"]
    assert agent.process_called is False
