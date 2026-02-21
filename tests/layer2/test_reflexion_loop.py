"""Тесты Reflexion Loop в TaskOrchestrator."""

import pytest
from unittest.mock import MagicMock

from vagus.layer2 import create_orchestrator_full


class _ReflexionRouter:
    """Роутер для теста полного цикла: плохой код -> оценка -> рефлексия -> хороший код."""

    def __init__(self):
        self._eval_call = 0
        self._coder_call = 0

    async def route_request(self, prompt: str, **kwargs):
        if "Return valid JSON" in prompt or "evaluation" in prompt.lower():
            self._eval_call += 1
            if self._eval_call == 1:
                yield {
                    "content": '{"score": 0.35, "issues": ["no tests"], "suggestions": ["add tests"]}',
                    "done": True,
                }
            else:
                yield {
                    "content": '{"score": 0.88, "issues": [], "suggestions": []}',
                    "done": True,
                }
        elif "Generate one refined prompt" in prompt or "reflection" in prompt.lower():
            yield {
                "content": "Напиши функцию сложения с проверкой типов и тестами. Добавь docstring.",
                "done": True,
            }
        else:
            self._coder_call += 1
            if self._coder_call == 1:
                yield {
                    "content": "```python\ndef add(a, b): return a + b\n```",
                    "done": True,
                }
            else:
                yield {
                    "content": "```python\ndef add(a, b):\n    \"\"\"Add two numbers.\"\"\"\n    return a + b\n\ndef test_add():\n    assert add(1, 2) == 3\n```",
                    "done": True,
                }


class _LowScoreAlwaysRouter:
    """Роутер: оценка всегда низкая, чтобы проверить лимит итераций."""

    def __init__(self):
        self._eval_calls = 0

    async def route_request(self, prompt: str, **kwargs):
        if "Return valid JSON" in prompt or "evaluation" in prompt.lower():
            self._eval_calls += 1
            yield {
                "content": '{"score": 0.2, "issues": ["bad"], "suggestions": ["fix"]}',
                "done": True,
            }
        elif "Generate one refined prompt" in prompt:
            yield {"content": "Улучшенный промпт: напиши код с тестами.", "done": True}
        else:
            yield {"content": "```python\ndef x(): pass\n```", "done": True}


@pytest.fixture
def reflexion_router():
    return _ReflexionRouter()


@pytest.fixture
def low_score_router():
    return _LowScoreAlwaysRouter()


@pytest.mark.asyncio
async def test_reflexion_loop_full_cycle(reflexion_router):
    """Полный цикл: плохой результат -> рефлексия -> улучшенный результат."""
    orch = create_orchestrator_full(reflexion_router)
    result = await orch.execute_task(
        task_id="reflex-1",
        prompt="Напиши функцию сложения двух чисел",
        task_type="code",
    )
    assert "error" not in result or result.get("error") is None
    assert result.get("success") is True
    assert "code" in result
    meta = result.get("metadata") or {}
    attempts = meta.get("reflexion_attempts", [])
    assert len(attempts) >= 1
    assert any(a.get("score", 0) >= 0.7 for a in attempts)


@pytest.mark.asyncio
async def test_max_iterations_limit(low_score_router):
    """Цикл прерывается после max_reflection_iterations."""
    orch = create_orchestrator_full(
        low_score_router,
        max_reflection_iterations=2,
    )
    result = await orch.execute_task(
        task_id="reflex-2",
        prompt="Напиши код",
        task_type="code",
    )
    assert "error" not in result or result.get("error") is None
    meta = result.get("metadata") or {}
    attempts = meta.get("reflexion_attempts", [])
    assert len(attempts) <= 2


@pytest.mark.asyncio
async def test_no_reflexion_for_evaluation_task():
    """Рефлексия не запускается для task_type=evaluation."""
    router = MagicMock()
    async def gen(p, **kw):
        yield {"content": '{"score": 0.9, "issues": [], "suggestions": []}', "done": True}
    router.route_request = gen
    orch = create_orchestrator_full(router)
    result = await orch.execute_task(
        task_id="eval-1",
        prompt="Оцени результат",
        task_type="evaluation",
        metadata={"original_prompt": "x", "agent_result": {"content": "ok"}},
    )
    meta = result.get("metadata") or {}
    assert "reflexion_attempts" not in meta or len(meta.get("reflexion_attempts", [])) == 0


@pytest.mark.asyncio
async def test_no_reflexion_for_reflection_task():
    """Рефлексия не запускается для task_type=reflection."""
    router = MagicMock()
    async def gen(p, **kw):
        yield {"content": "Refined prompt", "done": True}
    router.route_request = gen
    orch = create_orchestrator_full(router)
    result = await orch.execute_task(
        task_id="ref-1",
        prompt="Рефлексия",
        task_type="reflection",
        metadata={
            "original_prompt": "x",
            "agent_result": {},
            "evaluation_result": {"score": 0.3, "issues": [], "suggestions": []},
        },
    )
    meta = result.get("metadata") or {}
    assert "reflexion_attempts" not in meta or len(meta.get("reflexion_attempts", [])) == 0


@pytest.mark.asyncio
async def test_reflexion_attempts_in_metadata(reflexion_router):
    """reflexion_attempts присутствует в metadata при выполнении цикла."""
    orch = create_orchestrator_full(reflexion_router)
    result = await orch.execute_task(
        task_id="reflex-3",
        prompt="Напиши функцию сложения",
        task_type="code",
    )
    meta = result.get("metadata") or {}
    attempts = meta.get("reflexion_attempts", [])
    assert isinstance(attempts, list)
    for a in attempts:
        assert "score" in a


@pytest.mark.asyncio
async def test_disable_reflexion_via_constructor():
    """enable_reflexion=False отключает цикл."""
    router = _ReflexionRouter()
    orch = create_orchestrator_full(router, enable_reflexion=False)
    result = await orch.execute_task(
        task_id="reflex-4",
        prompt="Напиши код",
        task_type="code",
    )
    meta = result.get("metadata") or {}
    assert "reflexion_attempts" not in meta


@pytest.mark.asyncio
async def test_disable_reflexion_via_metadata():
    """metadata.enable_reflexion=False отключает цикл для задачи."""
    router = _ReflexionRouter()
    orch = create_orchestrator_full(router)
    result = await orch.execute_task(
        task_id="reflex-5",
        prompt="Напиши код",
        task_type="code",
        metadata={"enable_reflexion": False},
    )
    meta = result.get("metadata") or {}
    assert "reflexion_attempts" not in meta
