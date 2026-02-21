"""
Пример использования MemoryManager с полной интеграцией памяти.
Демонстрирует EpisodicMemory, SemanticMemory, ProceduralMemory и get_context_for_task.

Запуск: PYTHONPATH=src python examples/memory_manager_usage.py

Примечание: при первом запуске с chromadb может загружаться модель эмбеддингов.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vagus.layer2.memory import (
    EpisodicMemory,
    MemoryManager,
    ProceduralMemory,
    SemanticMemory,
)


async def main():
    # MemoryManager с in-memory хранилищами
    episodic = EpisodicMemory(":memory:")
    procedural = ProceduralMemory(":memory:")

    try:
        import chromadb

        semantic = SemanticMemory(chroma_client=chromadb.EphemeralClient())
        use_semantic = True
    except ImportError:
        semantic = SemanticMemory()
        use_semantic = True

    mgr = MemoryManager(
        episodic_memory=episodic,
        semantic_memory=semantic,
        procedural_memory=procedural,
    )

    tenant_id = "demo_tenant"
    task_id = "task_001"

    # 1. Сохраняем шаг в эпизодическую память
    step_id = await mgr.save_episodic_step(
        tenant_id=tenant_id,
        task_id=task_id,
        agent_type="coder",
        action="execute",
        result={"output": "Parsed 10 records"},
        metadata={"source": "example"},
    )
    print(f"Saved episodic step: {step_id}")

    # 2. Добавляем документ в семантическую память
    if use_semantic:
        try:
            await semantic.add_document_async(
                "How to parse JSON in Python: use json.loads()",
                {"tenant_id": tenant_id},
            )
            print("Added document to semantic memory")
        except Exception as e:
            print(f"Semantic add failed (optional): {e}")

    # 3. Сохраняем план в процедурную память
    plan_json = json.dumps(
        {
            "steps": [
                {"agent_type": "researcher", "prompt": "Search for best practices"},
                {"agent_type": "coder", "prompt": "Implement based on findings"},
            ]
        }
    )
    plan_id = await procedural.save_plan(
        tenant_id, "search analyze implement", plan_json, success_score=0.85
    )
    print(f"Saved procedural plan: {plan_id}")

    # 4. Получаем полный контекст для задачи
    task = {
        "task_id": task_id,
        "description": "Parse JSON data in Python",
        "intent_summary": "search analyze implement",
    }
    context = await mgr.get_context_for_task(task, tenant_id)

    # 5. Выводим собранный контекст
    print("\n--- Context for task ---")
    print(f"tenant_id: {context['tenant_id']}")
    print(f"task_id: {context['task_id']}")
    print(f"history steps: {len(context['history'])}")
    for i, step in enumerate(context["history"]):
        print(f"  [{i}] {step.get('agent_type')}: {step.get('action')} -> {step.get('result')}")
    print(f"relevant_knowledge: {len(context['relevant_knowledge'])} items")
    for i, doc in enumerate(context["relevant_knowledge"][:3]):
        print(f"  [{i}] {doc.get('text', '')[:60]}...")
    print(f"similar_plans: {len(context['similar_plans'])}")
    for i, plan in enumerate(context["similar_plans"][:2]):
        steps = plan.get("steps", [])
        print(f"  [{i}] {len(steps)} steps: {[s.get('agent_type') for s in steps]}")


if __name__ == "__main__":
    asyncio.run(main())
