"""Tests for Dead Letter Queue storage and orchestrator integration."""

import pytest

from vagus.layer2.communication import CommunicationLayer
from vagus.layer2.dead_letter_queue import DeadLetterQueueStorage
from vagus.layer2.orchestrator import TaskOrchestrator
from vagus.layer2.agents.base_agent import BaseAgent


class _FailingAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="analyst", llm_router=None, description="failing")

    async def process(self, task, context=None):
        raise RuntimeError("LLM unavailable")

    def can_handle(self, task_type: str) -> bool:
        return True


def test_dead_letter_queue_storage_insert_and_list(tmp_path):
    storage = DeadLetterQueueStorage(str(tmp_path / "dlq.db"))
    storage.add_failed_task(
        task_id="task-1",
        agent_type="coder",
        error_message="timeout",
        stack_trace="trace",
        retry_count=2,
        task_payload={"prompt": "hello", "task_type": "code"},
    )
    rows = storage.list_entries(limit=10)
    assert len(rows) == 1
    assert rows[0]["task_id"] == "task-1"
    assert rows[0]["agent_type"] == "coder"
    assert rows[0]["retry_count"] == 2
    assert rows[0]["task_payload"]["prompt"] == "hello"


def test_dead_letter_queue_manual_fix_and_retry_state(tmp_path):
    storage = DeadLetterQueueStorage(str(tmp_path / "dlq-state.db"))
    storage.add_failed_task(
        task_id="task-2",
        agent_type="researcher",
        error_message="network_error",
        stack_trace="trace",
    )
    assert storage.mark_retry_requested(task_id="task-2", retry_count=1) is True
    row = storage.get_latest_entry("task-2")
    assert row is not None
    assert row["status"] == "retry_requested"
    assert row["retry_count"] == 1

    assert storage.mark_manual_fix(task_id="task-2", note="fixed manually") is True
    row = storage.get_latest_entry("task-2")
    assert row is not None
    assert row["status"] == "manually_fixed"
    assert row["manual_fix_note"] == "fixed manually"


@pytest.mark.asyncio
async def test_orchestrator_records_exception_into_dead_letter_queue(tmp_path):
    dlq = DeadLetterQueueStorage(str(tmp_path / "dlq-orch.db"))
    orch = TaskOrchestrator(
        communication=CommunicationLayer(),
        dead_letter_queue=dlq,
    )
    orch.register_agent(_FailingAgent())

    result = await orch.execute_task("dlq-task", "анализируй", task_type="analysis")
    assert "error" in result
    assert "LLM unavailable" in result["error"]

    rows = dlq.list_entries(limit=5)
    assert rows
    assert rows[0]["task_id"] == "dlq-task"
    assert rows[0]["agent_type"] == "analyst"
    assert "LLM unavailable" in rows[0]["error_message"]
