# План реализации Слоя 2 от Manus AI
## Проектирование Агентной Системы (Слой 2) для Vagus Asistent

**Автор:** Manus AI  
**Версия:** 1.0  
**Дата:** Февраль 2026

---

## 📋 Содержание
1. [Обзор архитектуры и выбор паттерна](#1-обзор-архитектуры-и-выбор-паттерна)
2. [Диаграмма архитектуры Слоя 2](#2-диаграмма-архитектуры-слоя-2)
3. [Описание компонентов](#3-описание-компонентов)
4. [Меж-агентная коммуникация](#4-меж-агентная-коммуникация)
5. [Система памяти](#5-система-памяти)
6. [Система навыков](#6-система-навыков)
7. [Система оценки](#7-система-оценки)
8. [Готовые решения и библиотеки](#8-готовые-решения-и-библиотеки)
9. [Подводные камни](#9-подводные-камни)
10. [План реализации на 6 недель](#10-план-реализации-на-6-недель)

---

## 1. Обзор архитектуры и выбор паттерна

### 1.1. Выбор архитектурного паттерна
**Orchestrator-Worker** (гибридный паттерн):
- Управляемость и предсказуемость
- Масштабируемость
- Эффективность (параллельное выполнение)
- Гибкость (инкапсуляция других паттернов)

### 1.2. Интеграция со Слоем 1 (LLMRouter)
**Все LLM-вызовы проходят через LLMRouter:**
- Централизованный контроль стоимости
- Автоматический выбор оптимальной модели
- Fallback при ошибках
- Бюджетирование и мониторинг

---

## 2. Диаграмма архитектуры Слоя 2

```
┌─────────────────────────────────────────────────────────┐
│                    ПОЛЬЗОВАТЕЛЬ                         │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                 TASK ORCHESTRATOR                       │
│  (State Machine: PENDING → IN_PROGRESS → COMPLETED)     │
└──────────────┬────────────────────┬─────────────────────┘
               │                    │
    ┌──────────▼──────────┐ ┌──────▼──────────┐
    │   COMMUNICATION     │ │   MEMORY        │
    │      LAYER          │ │    SYSTEM       │
    │  (asyncio.Queue)    │ │(Episodic/Semantic)│
    └──────────┬──────────┘ └──────────────────┘
               │
    ┌──────────▼──────────────────────────────┐
    │          SPECIALIZED AGENTS             │
    ├─────────────────────────────────────────┤
    │  • Researcher Agent  • Coder Agent      │
    │  • Analyst Agent     • Summarizer Agent │
    └─────────────────────────────────────────┘
               │
    ┌──────────▼──────────┐
    │    SKILL SYSTEM     │
    │  (Tools Registry)   │
    └─────────────────────┘
```

---

## 3. Описание компонентов

| Компонент | Статус | Описание |
|-----------|--------|----------|
| **Task Orchestrator** | Критический | Мозг системы. Декомпозиция задач, управление state machine |
| **Specialized Agents** | Критический | Рабочие лошадки (Researcher, Coder, Analyst, Summarizer) |
| **Communication Layer** | Критический | Нервная система. asyncio.Queue → Redis в production |
| **Skill System** | Критический | Набор инструментов (search_web, execute_code, read_file) |
| **Memory System** | Критический (MVP) | Episodic (краткосрочная) + Semantic (долгосрочная) |
| **Agent Manager** | Опциональный | Динамическое масштабирование агентов |
| **Evaluation System** | Опциональный | Оценка качества работы агентов |

---

## 4. Меж-агентная коммуникация

### 4.1. Communication Layer (asyncio.Queue)
```python
# vagus/layer2/communication.py
import asyncio
from collections import defaultdict

class CommunicationLayer:
    def __init__(self):
        self.topics = defaultdict(asyncio.Queue)
        self.results = defaultdict(asyncio.Queue)
        self.subscribers = defaultdict(list)
    
    async def publish(self, topic: str, message: dict):
        for callback in self.subscribers.get(topic, []):
            asyncio.create_task(callback(message))
    
    async def subscribe(self, topic: str, callback):
        self.subscribers[topic].append(callback)
    
    async def publish_result(self, task_id: str, result: Any):
        await self.results[task_id].put(result)
    
    async def subscribe_to_result(self, task_id: str, timeout: int = 300) -> Any:
        try:
            return await asyncio.wait_for(self.results[task_id].get(), timeout=timeout)
        except asyncio.TimeoutError:
            return {"error": f"Task {task_id} timed out"}
```

---

## 5. Система памяти

### 5.1. Episodic Memory (краткосрочная)
```python
# vagus/layer2/memory/episodic.py
from typing import Dict, List, Tuple, Any
from datetime import datetime
from collections import defaultdict

class EpisodicMemory:
    def __init__(self):
        self.history = defaultdict(list)
    
    def add_step(self, task_id: str, step_name: str, details: Any):
        self.history[task_id].append((datetime.utcnow(), step_name, details))
    
    def get_history(self, task_id: str) -> List[Tuple[datetime, str, Any]]:
        return self.history.get(task_id, [])
```

### 5.2. Semantic Memory (долгосрочная, ChromaDB)
```python
# vagus/layer2/memory/semantic.py
import chromadb

class SemanticMemory:
    def __init__(self, path="./chroma_db"):
        self.client = chromadb.PersistentClient(path=path)
        self.collection = self.client.get_or_create_collection(name="vagus_semantic_memory")
    
    def add_fact(self, fact_id: str, fact: str, metadata: dict):
        self.collection.add(documents=[fact], metadatas=[metadata], ids=[fact_id])
    
    def search_facts(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        return self.collection.query(query_texts=[query], n_results=n_results)
```

---

## 6. Система навыков

### 6.1. Skill System Registry
```python
# vagus/layer2/skills/__init__.py
from typing import Dict, Callable, Any, Awaitable

class SkillSystem:
    def __init__(self):
        self._skills = {}
        self._register_default_skills()
    
    def _register_default_skills(self):
        self.register_skill("search_web", self.search_web)
        self.register_skill("execute_python_code", self.execute_python_code)
        self.register_skill("read_file", self.read_file)
    
    def register_skill(self, name: str, func: Callable[..., Awaitable[Any]]):
        self._skills[name] = func
    
    async def use_skill(self, name: str, **kwargs) -> Any:
        if name not in self._skills:
            return {"error": f"Skill '{name}' not found."}
        try:
            return await self._skills[name](**kwargs)
        except Exception as e:
            return {"error": f"Error executing skill '{name}': {e}"}
    
    # Примеры навыков
    async def search_web(self, query: str) -> str:
        return f"Результаты поиска по запросу '{query}': ..."
    
    async def execute_python_code(self, code: str) -> Dict[str, Any]:
        try:
            local_vars = {}
            exec(code, {}, local_vars)
            return {"status": "success", "output": local_vars}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    async def read_file(self, path: str) -> str:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {e}"
```

---

## 7. Система оценки

### 7.1. Evaluation System
```python
# vagus/layer2/evaluation.py
from typing import Dict, Any

class EvaluationSystem:
    def __init__(self, llm_router):
        self.llm_router = llm_router
    
    async def evaluate_task_output(self, task_description: str, output: Any) -> Dict[str, Any]:
        eval_results = {}
        relevance_score = await self.model_based_relevance_grader(task_description, output)
        eval_results['relevance'] = relevance_score
        return eval_results
    
    async def model_based_relevance_grader(self, description: str, output: str) -> float:
        prompt = f"""Оцени релевантность ответа на запрос по шкале 0.0-1.0.
        Запрос: {description}
        Ответ: {output}
        Оценка (0.0-1.0):"""
        
        try:
            response = await self.llm_router.route_request(prompt, quality='ultra')
            return float(response.content.strip())
        except (ValueError, TypeError):
            return 0.0
```

---

## 8. Готовые решения и библиотеки

| Библиотека | Назначение |
|------------|------------|
| **pydantic v2** | Валидация данных, конфигурация |
| **asyncio** | Асинхронное выполнение задач |
| **chromadb** | Векторная БД для Semantic Memory |
| **opentelemetry-sdk** | Трассировка и мониторинг |
| **pytest-asyncio** | Тестирование асинхронного кода |
| **redis** (опционально) | Production Communication Layer |

---

## 9. Подводные камни

| Проблема | Решение |
|----------|---------|
| **Token Burn** | Guardrails, лимиты на глубину рекурсии |
| **Бесконечные циклы** | Circuit Breaker для меж-агентных вызовов |
| **Каскадные сбои** | Graceful degradation, изоляция ошибок |
| **Prompt Injection** | Экранирование данных, валидация |
| **Отсутствие наблюдаемости** | Сквозная трассировка (trace_id) |

---

## 10. План реализации на 6 недель

### **Неделя 1: Ядро системы**
- Настройка структуры Слоя 2
- Реализация CommunicationLayer на asyncio.Queue
- Создание BaseAgent и TaskOrchestrator
- Интеграция с LLMRouter из Слоя 1

### **Неделя 2: Первый E2E сценарий**
- Реализация SkillSystem с search_web
- Реализация ResearcherAgent
- TaskOrchestrator: декомпозиция → выполнение → агрегация
- Первый интеграционный тест

### **Неделя 3: Расширение агентов**
- Добавление CoderAgent и навыка execute_python_code
- TaskOrchestrator: выбор агента по типу задачи
- Реализация EpisodicMemory
- Unit-тесты для всех компонентов

### **Неделя 4: Многошаговые задачи**
- Поддержка последовательного выполнения шагов
- Агрегация результатов от нескольких шагов
- Улучшение логики TaskOrchestrator
- Покрытие кода тестами

### **Неделя 5: Параллельное выполнение**
- Параллельное выполнение независимых подзадач
- Интеграция SemanticMemory (ChromaDB)
- Добавление SummarizerAgent
- Нагрузочное тестирование

### **Неделя 6: Стабилизация**
- Guardrails (ограничение глубины рекурсии)
- Исправление узких мест
- Документация API и архитектуры
- Подготовка к демонстрации MVP

---

## 🚀 КОМАНДЫ ДЛЯ НАЧАЛА

```bash
# 1. Перейти в папку проекта
cd "c:\Users\kopca\OneDrive\Desktop\Cursor Ai\Vagus_Asistent"

# 2. Создать структуру Слоя 2
mkdir -p src/vagus/layer2/{agents,communication,memory,skills}

# 3. Начать с Communication Layer
# Создать файл: src/vagus/layer2/communication.py
# Использовать код из раздела 4.1

# 4. Создать BaseAgent
# Создать файл: src/vagus/layer2/agents/base_agent.py

# 5. Создать TaskOrchestrator  
# Создать файл: src/vagus/layer2/orchestrator.py
```

---

## 11. Результаты реализации (Февраль 2026)

### Реализовано

| Компонент | Статус | Описание |
|-----------|--------|----------|
| **TaskOrchestrator** | ✅ | execute_task, execute_multi_step_task, execute_parallel_tasks |
| **ResearcherAgent** | ✅ | Поиск + LLM синтез |
| **CoderAgent** | ✅ | Генерация и выполнение кода |
| **AnalystAgent** | ✅ | Анализ данных, статистика |
| **EpisodicMemory** | ✅ | add_step, get_history, add_steps_batch |
| **SemanticMemory** | ✅ | Векторный поиск, кэш эмбеддингов |
| **SkillSystem** | ✅ | search_web, execute_python_code, read_file |
| **Параллельное выполнение** | ✅ | asyncio.gather + Semaphore |
| **Интеграция памяти** | ✅ | Episodic + Semantic в Orchestrator |

### Тесты: 69+ unit и E2E тестов
- test_analyst_agent, test_coder_agent, test_researcher_agent
- test_episodic_memory, test_semantic_memory, test_similar_tasks
- test_parallel_tasks, test_multi_step_tasks
- test_resilience, test_edge_cases, test_full_integration

---

## 📞 КОНТАКТЫ
- **Проект:** Vagus Asistent
- **Репозиторий:** https://github.com/kopcaptz/VAGUS-ASISTENT
- **Слой 1:** Готов и протестирован
- **Слой 2:** MVP реализован (Дни 1–6)

---

**✅ ПЛАН ГОТОВ К ИСПОЛЬЗОВАНИЮ CURSOR!**