"""Shared typed structures for Layer2 orchestration and agents."""

from __future__ import annotations

from typing import Any, TypedDict


class AgentMetadata(TypedDict, total=False):
    """Optional metadata passed with tasks and emitted with results."""

    retry_count: int
    task_type: str
    prompt: str
    step_index: int
    parent_task_id: str
    degraded: bool
    reason: str
    fallback_strategy: str
    agent: str


class AgentTask(TypedDict, total=False):
    """Input payload processed by specialized agents."""

    task_id: str
    prompt: str
    task_type: str
    metadata: AgentMetadata | dict[str, Any]
    requirements: dict[str, Any]
    style: str
    framework: str
    use_llm: bool
    base_color: str


class AgentResult(TypedDict, total=False):
    """Generic result payload returned by specialized agents."""

    content: str
    error: str
    metadata: AgentMetadata | dict[str, Any]
    success: bool
    code: str
    search_raw: Any
    recommendations: Any
    analysis: Any
    layout: Any
    generated_ui: Any
    accessibility_report: Any
    palette: Any
    step_index: int
    results: dict[str, Any]
    errors: dict[str, str]
    completed_count: int
    total_count: int
    steps_results: list[dict[str, Any]]
    step_count: int
    context: dict[str, Any]


class AgentContext(TypedDict, total=False):
    """Context passed between steps in multi-step orchestration."""

    previous_steps: list[dict[str, Any]]


class MultiStepTask(TypedDict, total=False):
    """Single step definition used by execute_multi_step_task()."""

    type: str
    prompt: str

