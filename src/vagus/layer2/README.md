# Слой 2: Агентная система Vagus

Orchestrator-Worker архитектура для Vagus Asistent.

## Компоненты

### TaskOrchestrator
Мозг системы. Методы:
- `execute_task(task_id, prompt, task_type)` — одна задача
- `execute_multi_step_task(task_id, steps)` — цепочка шагов (research → code → analysis)
- `execute_parallel_tasks(task_ids, prompts, task_types, max_concurrency)` — параллельное выполнение

### Агенты
| Агент | Типы задач |
|-------|------------|
| ResearcherAgent | research, search, find |
| CoderAgent | code, programming, script, python |
| AnalystAgent | analysis, statistics, insights, report |

### Память
- **EpisodicMemory** — история выполнения (add_step, get_history, add_steps_batch)
- **SemanticMemory** — векторный поиск похожих задач (add_embedding, search_similar, get_context)
- Автоматическая синхронизация: Episodic → Semantic после каждой задачи

### SkillSystem
- `search_web` — поиск в интернете
- `execute_python_code` — выполнение кода
- `read_file` — чтение файлов

## Примеры использования

### Быстрый старт
```python
from vagus.layer2 import create_orchestrator_full
from vagus.layer1.router import LLMRouter

router = LLMRouter(...)
await router.initialize()
orchestrator = create_orchestrator_full(router)

# Одна задача
result = await orchestrator.execute_task("t1", "Напиши функцию сложения", "code")

# Многошаговая
result = await orchestrator.execute_multi_step_task("m1", [
    {"type": "research", "prompt": "Найди информацию о Python"},
    {"type": "code", "prompt": "Напиши пример"},
    {"type": "analysis", "prompt": "Проанализируй результат"},
])

# Параллельные задачи
result = await orchestrator.execute_parallel_tasks(
    task_ids=["p1", "p2", "p3"],
    prompts=["Задача 1", "Задача 2", "Задача 3"],
    max_concurrency=3,
)
```

### Доступ к памяти
```python
orchestrator = create_orchestrator_full(router)

# EpisodicMemory
history = orchestrator.memory.get_history("task_id")
summary = orchestrator.memory.get_task_summary("task_id")

# SemanticMemory
similar = orchestrator.semantic_memory.search_similar("похожий запрос", top_k=3)
context = orchestrator.semantic_memory.get_context("новый промпт")
```

### Собственный оркестратор
```python
from vagus.layer2 import (
    CommunicationLayer,
    EpisodicMemory,
    SemanticMemory,
    TaskOrchestrator,
    ResearcherAgent,
    CoderAgent,
    AnalystAgent,
    SkillSystem,
)

comm = CommunicationLayer()
memory = EpisodicMemory()
semantic = SemanticMemory()
skill_system = SkillSystem()

orch = TaskOrchestrator(communication=comm, memory=memory, semantic_memory=semantic)
orch.register_agent(ResearcherAgent(llm_router, skill_system))
orch.register_agent(CoderAgent(llm_router, skill_system))
orch.register_agent(AnalystAgent(llm_router))
```

## Запуск тестов

```bash
PYTHONPATH=src pytest tests/layer2/ -v
```

## Оптимизации

- **SemanticMemory**: кэширование эмбеддингов запросов
- **EpisodicMemory**: batch-операция add_steps_batch
- **execute_parallel_tasks**: Semaphore для ограничения параллелизма
