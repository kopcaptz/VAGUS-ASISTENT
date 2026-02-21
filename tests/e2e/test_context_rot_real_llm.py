"""
E2E tests: Context Rot with real LLM.

Verifies CoherenceMonitor.summarize_and_replace() works correctly in long conversations:
- 55+ steps in a single task
- History is compressed via summarization
- Critical facts are preserved
- History size does not grow unbounded
"""
import os
import pytest

from vagus.layer2 import create_master_orchestrator_full

# Critical facts injected in steps 5, 25, 45 for verification
CRITICAL_FACTS = ["Alice", "March1", "March 1"]
PLAN_ID = "plan_ctx_rot_test"


def _make_55_step_plan(plan_id: str = PLAN_ID) -> dict:
    """Generate a 55-step plan with critical facts at steps 6, 26, 46 (0-indexed: 5, 25, 45)."""
    steps = []
    for i in range(55):
        agent = "researcher" if i % 2 == 0 else "coder"
        if i in (5, 25, 45):
            prompt = f"Step {i + 1}: User is Alice, deadline March 1."
        else:
            prompt = f"Step {i + 1} trivial task."
        steps.append({
            "step_id": f"s{i + 1}",
            "agent_type": agent,
            "prompt": prompt,
            "depends_on": [f"s{i}"] if i > 0 else [],
            "artefact_key": f"step_{i + 1}",
        })
    return {"plan_id": plan_id, "steps": steps, "execution_mode": "sequential"}


def _mock_agent_process(agent):
    """Replace agent.process with a mock that returns content with embedded facts."""

    async def _process(task, context=None):
        prompt = (task.get("prompt") or "").lower()
        content = "Step completed."
        if "alice" in prompt:
            content = "User Alice confirmed. Deadline March 1."
        elif "march 1" in prompt or "march1" in prompt:
            content = "Deadline March 1 noted."
        return {"content": content, "metadata": {}}

    agent.process = _process
    return agent


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY") and not os.getenv("DEEPSEEK_API_KEY"),
    reason="OPENAI_API_KEY or DEEPSEEK_API_KEY required for E2E Context Rot tests",
)
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_long_conversation_context_rot(real_llm_router, layer2_context_rot_config):
    """
    1. Create MasterOrchestrator with real LLM
    2. Execute 55 sequential steps in one plan
    3. Verify CoherenceMonitor was triggered (summary steps exist)
    4. Verify critical facts preserved in history
    5. Verify history size is bounded (< 30 steps)
    """
    orch = create_master_orchestrator_full(
        real_llm_router,
        layer2_config=layer2_context_rot_config,
    )

    # Mock task planner to return 55-step plan
    plan_55 = _make_55_step_plan()
    async def _mock_create_plan(_intent):
        return plan_55
    orch.task_planner.create_plan = _mock_create_plan

    # Mock intent classifier
    async def _mock_classify(_):
        return {
            "primary_intent": "research",
            "sub_intents": [],
            "entities": {},
            "complexity": "simple",
            "confidence": 0.9,
        }
    orch.intent_classifier.classify = _mock_classify

    # Mock agents to return controlled content (facts embedded for summarizer to preserve)
    for agent in orch.agent_registry.list():
        _mock_agent_process(agent)

    # Run one process_request - executes all 55 steps
    result = await orch.process_request("Long conversation for context rot test")

    assert "content" in result
    assert "metadata" in result
    plan_id = result["metadata"].get("plan_id")
    assert plan_id

    # 1. Verify CoherenceMonitor was triggered: summary steps exist
    tenant_id = orch.config.get("tenant_id", "default") if orch.config else "default"
    history = await orch.memory_manager.episodic.get_recent_history(
        tenant_id, plan_id, limit=100
    )

    summary_steps = [
        s for s in history
        if s.get("agent_type") == "summarizer"
        or s.get("metadata", {}).get("compressed")
    ]
    assert len(summary_steps) >= 2, (
        f"Expected at least 2 summarization cycles (threshold=20), got {len(summary_steps)}"
    )

    # 2. Verify history size is bounded
    assert len(history) < 30, (
        f"History should be compressed (< 30 steps), got {len(history)}"
    )

    # 3. Verify critical facts preserved in summary or recent steps
    all_text = " ".join(
        str(s.get("result", {}).get("content", ""))
        for s in history
    )
    found_facts = [f for f in CRITICAL_FACTS if f in all_text]
    assert len(found_facts) >= 1, (
        f"Expected at least one of {CRITICAL_FACTS} preserved, got: {all_text[:500]}"
    )
