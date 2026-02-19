"""Полный интеграционный E2E тест: все агенты и типы памяти вместе."""
import pytest
from unittest.mock import MagicMock

from vagus.layer2 import create_orchestrator_full


async def _mock_llm_universal(prompt: str, **kwargs):
    """Универсальный мок: разный контент по ключевым словам.
    Порядок важен: код/скрипт проверяем до поиска (контекст может содержать «найди»).
    """
    lower = prompt.lower()
    # Код — проверяем первым, т.к. контекст может содержать «найди»
    if "скрипт" in lower or "код" in lower or "функция" in lower or "вычисл" in lower:
        yield {"content": "```python\ndef solve(): return 42\n```", "done": True}
    elif "найди" in lower or "поиск" in lower or "информаци" in lower:
        yield {"content": "Результаты поиска: Python — популярный язык.", "done": True}
    elif "анализ" in lower or "проанализируй" in lower or "тренд" in lower:
        yield {"content": "Анализ: среднее 50, тренд положительный.", "done": True}
    else:
        yield {"content": "Общий ответ.", "done": True}


@pytest.fixture
def full_system():
    """Полная система: все агенты, Episodic + Semantic memory."""
    router = MagicMock()
    router.route_request = _mock_llm_universal
    return create_orchestrator_full(router)


@pytest.mark.asyncio
async def test_full_e2e_prompt_to_result(full_system):
    """
    Полный E2E: от промпта до результата.
    Последовательность: research -> code -> analysis.
    """
    orch = full_system

    # 1. Исследование
    r1 = await orch.execute_task("full-1", "Найди информацию о Python", task_type="research")
    assert "content" in r1
    assert "Python" in r1.get("content", "")

    # 2. Код
    r2 = await orch.execute_task("full-2", "Напиши функцию вычисления", task_type="code")
    assert r2.get("success") is True
    assert "code" in r2

    # 3. Анализ
    r3 = await orch.execute_task("full-3", "Проанализируй данные [1,2,3]", task_type="analysis")
    assert "content" in r3


@pytest.mark.asyncio
async def test_full_e2e_all_agents_together(full_system):
    """Все агенты работают в одной системе."""
    orch = full_system
    memory = orch.memory
    semantic = orch.semantic_memory

    tasks = [
        ("agent-r", "Найди информацию о asyncio", "research"),
        ("agent-c", "Напиши скрипт для суммы", "code"),
        ("agent-a", "Сделай анализ тренда", "analysis"),
    ]

    for task_id, prompt, ttype in tasks:
        result = await orch.execute_task(task_id, prompt, task_type=ttype)
        assert "error" not in result or not result.get("error")

    # EpisodicMemory: все задачи записаны
    for tid, _, _ in tasks:
        assert len(memory.get_history(tid)) >= 1

    # SemanticMemory: похожие задачи находятся
    similar = semantic.search_similar("скрипт сумма", top_k=1)
    assert len(similar) >= 1


@pytest.mark.asyncio
async def test_full_e2e_multi_step_and_parallel(full_system):
    """Многошаговая + параллельные задачи в одной сессии."""
    orch = full_system

    # Многошаговая
    multi = await orch.execute_multi_step_task("multi-full", [
        {"type": "code", "prompt": "Код для x=1"},
        {"type": "analysis", "prompt": "Анализ результата"},
    ])
    assert "steps_results" in multi
    assert len(multi["steps_results"]) == 2

    # Параллельные
    parallel = await orch.execute_parallel_tasks(
        task_ids=["pa1", "pa2"],
        prompts=["Параллельный 1", "Параллельный 2"],
        task_types=["analysis", "analysis"],
    )
    assert parallel["completed_count"] == 2
