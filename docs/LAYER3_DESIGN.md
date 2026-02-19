# ДИЗАЙН-ДОКУМЕНТ: СЛОЙ 3 — ИНТЕРФЕЙСЫ

**Проект:** Vagus Asistent
**Слой:** 3 (Interfaces Layer)
**Статус:** 📋 Проектирование
**Автор:** Manus AI
**Дата создания:** 2026-02-19
**Зависимости:** Слой 0 (Фундамент ✅), Слой 1 (LLM Router ✅), Слой 2 (Оркестрация 🚧)

---

## 📋 СОДЕРЖАНИЕ

1. [Философия и Принципы Дизайна](#1-философия-и-принципы-дизайна)
2. [Общая Архитектура Слоя 3](#2-общая-архитектура-слоя-3)
3. [Технологический Стек: Обоснование Выбора](#3-технологический-стек-обоснование-выбора)
4. [REST API — Ядро Слоя 3](#4-rest-api--ядро-слоя-3)
5. [Web Dashboard](#5-web-dashboard)
6. [CLI (Command-Line Interface)](#6-cli-command-line-interface)
7. [Channel Gateway (Chat Bots)](#7-channel-gateway-chat-bots)
8. [Интеграция со Слоем 2](#8-интеграция-со-слоем-2)
9. [Безопасность: Аутентификация и Авторизация](#9-безопасность-аутентификация-и-авторизация)
10. [Структура Файлов Проекта](#10-структура-файлов-проекта)
11. [План Реализации](#11-план-реализации)
12. [Подводные Камни и Решения](#12-подводные-камни-и-решения)
13. [Промпты для Kursor AI Mob](#13-промпты-для-kursor-ai-mob)

---

## 1. Философия и Принципы Дизайна

Слой 3 является **лицом системы Vagus Asistent**. Он превращает мощный, но сложный внутренний механизм (Слои 0–2) в набор удобных, безопасных и интуитивно понятных интерфейсов для разных категорий пользователей. Дизайн Слоя 3 строится на четырёх фундаментальных принципах.

**Принцип 1: Единая Точка Входа (Single Entry Point).** Все внешние взаимодействия с системой — будь то HTTP-запрос от веб-приложения, команда из консоли или сообщение в Telegram — проходят через единый централизованный шлюз (API Gateway). Это обеспечивает унифицированную аутентификацию, авторизацию, логирование и управление нагрузкой в одном месте.

**Принцип 2: Клиент-Серверная Изоляция.** Ни один из интерфейсов (Dashboard, CLI, Chat Bot) не взаимодействует напрямую с `TaskOrchestrator` или `LLMRouter`. Все они являются **клиентами** для REST API. Это обеспечивает слабую связанность (loose coupling): внутренняя реализация Слоёв 1 и 2 может меняться, не затрагивая интерфейсы.

**Принцип 3: Асинхронность по умолчанию.** Весь стек Слоя 3 построен на `asyncio`, что соответствует архитектуре нижних слоёв и обеспечивает высокую производительность при обработке большого числа одновременных запросов.

**Принцип 4: Наблюдаемость (Observability).** Каждый запрос, проходящий через Слой 3, получает уникальный `trace_id`, который передаётся в Слой 2 и далее в Слой 1. Это позволяет отслеживать полный жизненный цикл любой задачи от момента получения запроса до финального ответа.

---

## 2. Общая Архитектура Слоя 3

Слой 3 состоит из четырёх независимых, но взаимосвязанных компонентов, каждый из которых обслуживает свою аудиторию.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ВНЕШНИЕ КЛИЕНТЫ                                  │
│                                                                     │
│  [Браузер/Web]  [Терминал/CLI]  [REST-клиент]  [Telegram/Discord]  │
└──────┬──────────────┬────────────────┬─────────────────┬───────────┘
       │              │                │                 │
       ▼              ▼                ▼                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         СЛОЙ 3: ИНТЕРФЕЙСЫ                          │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────────────┐ │
│  │ Web Dashboard│  │     CLI     │  │      Channel Gateway         │ │
│  │ (Streamlit) │  │   (Typer)   │  │  (aiogram / nextcord)        │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────────┬───────────────┘ │
│         │                │                         │                 │
│         └────────────────┼─────────────────────────┘                 │
│                          ▼                                           │
│              ┌───────────────────────┐                               │
│              │  API Gateway (FastAPI)│  ◄── Прямые REST-клиенты     │
│              │  /api/v1/...          │                               │
│              │  /ws/v1/...           │                               │
│              └───────────┬───────────┘                               │
└──────────────────────────┼──────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         СЛОЙ 2: ОРКЕСТРАЦИЯ                         │
│              ┌────────────────────────────────┐                     │
│              │       TaskOrchestrator         │                     │
│              │  (execute_task, agents, ...)   │                     │
│              └────────────────────────────────┘                     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Технологический Стек: Обоснование Выбора

### 3.1. FastAPI vs Flask

Выбор между FastAPI и Flask является ключевым решением для ядра Слоя 3. Анализ показывает однозначное преимущество FastAPI для данного проекта.

| Критерий                   | FastAPI                                              | Flask                                                |
| :------------------------- | :--------------------------------------------------- | :--------------------------------------------------- |
| **Производительность**     | 15 000–20 000 req/s (async, ASGI)                    | 2 000–3 000 req/s (sync, WSGI)                       |
| **Асинхронность**          | Нативная (`async def`), основана на Starlette/ASGI   | Требует расширений (Flask-Async, Quart)              |
| **Валидация данных**       | Встроенная через Pydantic v2                         | Требует сторонних библиотек (Marshmallow, WTForms)   |
| **Документация API**       | Автоматическая генерация OpenAPI (Swagger + ReDoc)   | Требует расширений (Flask-RESTX, Flasgger)           |
| **Dependency Injection**   | Встроенная, мощная система `Depends`                 | Отсутствует, требует ручной реализации               |
| **WebSocket**              | Встроенная поддержка                                 | Требует расширений (Flask-SocketIO)                  |
| **Совместимость с проектом** | Полная: `asyncio`, Pydantic уже используется в Слое 0 | Частичная: требует адаптации                        |

**Вердикт:** FastAPI является единственным обоснованным выбором для Слоя 3, поскольку он нативно совместим с асинхронной архитектурой всего проекта и предоставляет все необходимые возможности "из коробки".

### 3.2. Streamlit vs Gradio

| Критерий                   | Streamlit                                            | Gradio                                               |
| :------------------------- | :--------------------------------------------------- | :--------------------------------------------------- |
| **Назначение**             | Дашборды, аналитика, сложные UI                      | Демонстрация ML-моделей, простые интерфейсы          |
| **Кастомизация**           | Высокая (CSS, HTML, кастомные компоненты)            | Ограниченная                                         |
| **Многостраничность**      | Встроенная поддержка (`pages/`)                      | Ограниченная (через Tabs)                            |
| **Визуализация данных**    | Отличная (Plotly, Altair, Matplotlib)                | Базовая                                              |
| **Опыт использования в проекте** | Уже используется в `Nano_Bot_V-2.0`           | Не используется                                      |
| **Интеграция с REST API**  | Простая через `requests` / `httpx`                   | Простая                                              |

**Вердикт:** Streamlit является очевидным выбором, так как он уже используется в `Nano_Bot_V-2.0` (в папке `dashboard/`), что означает наличие готовых паттернов и опыта в команде. Его возможности для создания сложных многостраничных дашбордов с богатой визуализацией данных полностью соответствуют требованиям.

### 3.3. Telegram: aiogram vs python-telegram-bot

| Критерий                   | aiogram 3.x                                          | python-telegram-bot                                  |
| :------------------------- | :--------------------------------------------------- | :--------------------------------------------------- |
| **Асинхронность**          | Полностью асинхронный (`asyncio`)                    | Поддерживает async, но исторически sync              |
| **Производительность**     | Высокая                                              | Средняя                                              |
| **FSM (машина состояний)** | Встроенная, мощная                                   | Требует дополнительных усилий                        |
| **Middleware**             | Встроенная поддержка                                 | Ограниченная                                         |
| **Совместимость с проектом** | Полная: `asyncio`, современный Python               | Частичная                                            |

**Вердикт:** `aiogram 3.x` является лучшим выбором для Telegram-бота благодаря полной асинхронности и мощным встроенным инструментам (FSM, middleware), которые необходимы для сложных диалоговых сценариев.

### 3.4. CLI: Typer vs Click

`Typer` является надстройкой над `Click` и использует Python type hints для автоматического создания CLI. Это делает код значительно чище и проще в поддержке. Поскольку FastAPI (используемый в Слое 3) создан тем же автором и использует ту же философию type hints, выбор `Typer` обеспечивает консистентность всего стека.

---

## 4. REST API — Ядро Слоя 3

### 4.1. Структура Эндпоинтов

API версионируется с помощью префикса `/api/v1/`. Это позволяет вносить несовместимые изменения в будущем, не нарушая работу существующих клиентов.

| Метод    | Эндпоинт                        | Описание                                                          | Аутентификация |
| :------- | :------------------------------ | :---------------------------------------------------------------- | :------------- |
| `POST`   | `/api/v1/auth/token`            | Получить JWT-токен по логину/паролю или API-ключу                 | Нет            |
| `POST`   | `/api/v1/auth/refresh`          | Обновить access_token с помощью refresh_token                     | Нет            |
| `POST`   | `/api/v1/tasks`                 | Создать новую задачу и получить её `task_id`                      | JWT            |
| `GET`    | `/api/v1/tasks/{task_id}`       | Получить статус и результат задачи                                | JWT            |
| `GET`    | `/api/v1/tasks`                 | Получить список задач текущего пользователя                       | JWT            |
| `DELETE` | `/api/v1/tasks/{task_id}`       | Отменить задачу (если она ещё выполняется)                        | JWT            |
| `GET`    | `/api/v1/agents`                | Получить список доступных агентов и их типы задач                 | JWT            |
| `GET`    | `/api/v1/status`                | Получить общее состояние системы (метрики Слоёв 1 и 2)            | JWT (admin)    |
| `WS`     | `/api/v1/tasks/ws/{task_id}`    | WebSocket для стриминга результатов задачи в реальном времени     | JWT (query)    |

### 4.2. Pydantic-модели Запросов и Ответов

Строгая типизация всех входящих и исходящих данных является ключевым требованием для надёжности API.

```python
# src/vagus/layer3/api/models.py

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from enum import Enum
from datetime import datetime


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# --- Запросы ---

class TaskCreateRequest(BaseModel):
    """Запрос на создание новой задачи."""
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="Основной запрос или команда для выполнения агентом"
    )
    task_type: str = Field(
        default="default",
        description="Тип задачи для выбора агента: 'research', 'code', 'default'"
    )
    stream: bool = Field(
        default=False,
        description="Если True, результат будет доступен через WebSocket"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Дополнительные метаданные (например, user_id из Telegram)"
    )


# --- Ответы ---

class TaskCreateResponse(BaseModel):
    """Ответ на создание задачи."""
    task_id: str = Field(..., description="Уникальный идентификатор задачи (UUID)")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    status_endpoint: str = Field(..., description="URL для опроса статуса задачи")
    stream_endpoint: str = Field(..., description="WebSocket URL для стриминга")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaskStatusResponse(BaseModel):
    """Ответ с текущим статусом задачи."""
    task_id: str
    status: TaskStatus
    result: Optional[Any] = Field(None, description="Результат выполнения (если COMPLETED)")
    error: Optional[str] = Field(None, description="Сообщение об ошибке (если FAILED)")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AgentInfoResponse(BaseModel):
    """Информация об агенте."""
    name: str
    description: str
    task_types: List[str]
    is_available: bool


class SystemStatusResponse(BaseModel):
    """Общее состояние системы."""
    layer1_stats: Dict[str, Any]
    layer2_agents_count: int
    active_tasks_count: int
    uptime_seconds: float


class WebSocketStreamChunk(BaseModel):
    """Один чанк стриминга через WebSocket."""
    content: Optional[str] = None
    done: bool = False
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
```

### 4.3. Структура Роутеров FastAPI

```python
# src/vagus/layer3/api/routers/tasks.py

import asyncio
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from ..models import TaskCreateRequest, TaskCreateResponse, TaskStatusResponse, TaskStatus
from ..dependencies import get_orchestrator, get_current_user
from vagus.layer2.orchestrator import TaskOrchestrator

router = APIRouter(prefix="/tasks", tags=["Tasks"])

# Хранилище статусов задач (в production — Redis или БД)
_task_store: dict[str, dict] = {}


@router.post("", response_model=TaskCreateResponse)
async def create_task(
    request: TaskCreateRequest,
    orchestrator: TaskOrchestrator = Depends(get_orchestrator),
    current_user: dict = Depends(get_current_user),
):
    """Создаёт новую задачу и запускает её выполнение в фоне."""
    task_id = str(uuid.uuid4())
    now = datetime.utcnow()

    _task_store[task_id] = {
        "task_id": task_id,
        "status": TaskStatus.PENDING,
        "result": None,
        "error": None,
        "metadata": {"user_id": current_user["sub"]},
        "created_at": now,
        "updated_at": now,
    }

    # Запуск задачи в фоне без блокировки ответа
    asyncio.create_task(
        _run_task(task_id, request, orchestrator)
    )

    return TaskCreateResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        status_endpoint=f"/api/v1/tasks/{task_id}",
        stream_endpoint=f"/api/v1/tasks/ws/{task_id}",
        created_at=now,
    )


async def _run_task(task_id: str, request: TaskCreateRequest, orchestrator: TaskOrchestrator):
    """Фоновая корутина для выполнения задачи."""
    _task_store[task_id]["status"] = TaskStatus.IN_PROGRESS
    _task_store[task_id]["updated_at"] = datetime.utcnow()
    try:
        result = await orchestrator.execute_task(
            task_id=task_id,
            prompt=request.prompt,
            task_type=request.task_type,
        )
        _task_store[task_id]["status"] = TaskStatus.COMPLETED
        _task_store[task_id]["result"] = result
    except Exception as e:
        _task_store[task_id]["status"] = TaskStatus.FAILED
        _task_store[task_id]["error"] = str(e)
    finally:
        _task_store[task_id]["updated_at"] = datetime.utcnow()


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Возвращает текущий статус и результат задачи."""
    task = _task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return TaskStatusResponse(**task)


@router.websocket("/ws/{task_id}")
async def stream_task_result(websocket: WebSocket, task_id: str):
    """WebSocket для стриминга результатов задачи в реальном времени."""
    await websocket.accept()
    try:
        while True:
            task = _task_store.get(task_id)
            if not task:
                await websocket.send_json({"error": "Task not found", "done": True})
                break
            if task["status"] == TaskStatus.COMPLETED:
                await websocket.send_json({
                    "content": str(task.get("result", "")),
                    "done": True
                })
                break
            elif task["status"] == TaskStatus.FAILED:
                await websocket.send_json({
                    "error": task.get("error", "Unknown error"),
                    "done": True
                })
                break
            else:
                await websocket.send_json({"content": None, "done": False})
                await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
```

### 4.4. Точка Входа FastAPI (main.py)

```python
# src/vagus/layer3/api/main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from vagus.layer0.config import ConfigManager
from vagus.layer0.logging import get_logger
from vagus.layer1 import LLMRouter
from vagus.layer2.orchestrator import TaskOrchestrator
from vagus.layer2.communication import CommunicationLayer
from vagus.layer2.agents.researcher import ResearcherAgent
from .routers import tasks_router, agents_router, status_router, auth_router

logger = get_logger("layer3.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    logger.info("Starting Vagus Asistent API Gateway...")

    # Инициализация Слоя 1
    llm_router = LLMRouter(
        enable_cache=True,
        enable_budgeting=True,
        enable_monitoring=True,
    )
    await llm_router.initialize()

    # Инициализация Слоя 2
    communication = CommunicationLayer()
    orchestrator = TaskOrchestrator(communication=communication)
    orchestrator.register_agent(ResearcherAgent(llm_router=llm_router))

    # Сохранение в состоянии приложения
    app.state.llm_router = llm_router
    app.state.orchestrator = orchestrator
    app.state.start_time = __import__("time").monotonic()

    logger.info("Vagus Asistent API Gateway is ready.")
    yield

    # Graceful shutdown
    logger.info("Shutting down Vagus Asistent API Gateway...")
    await llm_router.shutdown()


app = FastAPI(
    title="Vagus Asistent API",
    description="Multi-layer AI agent system with LLM routing",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS для Web Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],  # Streamlit
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(status_router, prefix="/api/v1")
```

---

## 5. Web Dashboard

### 5.1. Концепция и Страницы

Web Dashboard построен на **Streamlit** и является многостраничным приложением. Каждая страница выполняет конкретную функцию и взаимодействует с системой исключительно через REST API.

```
dashboard/
├── main.py                    # Точка входа, конфигурация страниц
├── pages/
│   ├── 1_Tasks.py             # Создание задач и просмотр результатов
│   ├── 2_Monitoring.py        # Метрики производительности и затрат
│   ├── 3_Agents.py            # Информация об агентах
│   └── 4_Settings.py          # Настройки (только для admin)
└── utils/
    ├── api_client.py          # HTTP-клиент для взаимодействия с REST API
    ├── auth.py                # Управление JWT-токеном в session_state
    └── charts.py              # Вспомогательные функции для визуализации
```

### 5.2. Клиент для REST API

Для взаимодействия с API используется вспомогательный класс, который инкапсулирует логику HTTP-запросов и управление токеном.

```python
# dashboard/utils/api_client.py

import httpx
import streamlit as st
from typing import Any, Dict, Optional

API_BASE_URL = "http://localhost:8000/api/v1"


class VagusAPIClient:
    """HTTP-клиент для взаимодействия с REST API Vagus Asistent."""

    def __init__(self):
        self._token: Optional[str] = st.session_state.get("access_token")

    @property
    def _headers(self) -> Dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    def login(self, username: str, password: str) -> bool:
        """Аутентификация и сохранение токена."""
        with httpx.Client() as client:
            resp = client.post(
                f"{API_BASE_URL}/auth/token",
                data={"username": username, "password": password}
            )
        if resp.status_code == 200:
            data = resp.json()
            st.session_state["access_token"] = data["access_token"]
            self._token = data["access_token"]
            return True
        return False

    def create_task(self, prompt: str, task_type: str = "default") -> Dict[str, Any]:
        """Создать новую задачу."""
        with httpx.Client() as client:
            resp = client.post(
                f"{API_BASE_URL}/tasks",
                json={"prompt": prompt, "task_type": task_type},
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Получить статус задачи."""
        with httpx.Client() as client:
            resp = client.get(
                f"{API_BASE_URL}/tasks/{task_id}",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()

    def get_system_status(self) -> Dict[str, Any]:
        """Получить статистику системы."""
        with httpx.Client() as client:
            resp = client.get(
                f"{API_BASE_URL}/status",
                headers=self._headers,
            )
        resp.raise_for_status()
        return resp.json()
```

### 5.3. Страница Задач (1_Tasks.py)

```python
# dashboard/pages/1_Tasks.py

import time
import streamlit as st
from dashboard.utils.api_client import VagusAPIClient
from dashboard.utils.auth import require_login

require_login()  # Редирект на страницу входа, если не аутентифицирован

st.title("🎯 Задачи")

client = VagusAPIClient()

# Форма создания задачи
with st.form("create_task_form"):
    prompt = st.text_area("Введите запрос:", height=150, placeholder="Напиши Python-функцию для...")
    task_type = st.selectbox("Тип задачи:", ["default", "research", "code"])
    submitted = st.form_submit_button("🚀 Запустить задачу")

if submitted and prompt:
    with st.spinner("Создание задачи..."):
        try:
            response = client.create_task(prompt=prompt, task_type=task_type)
            task_id = response["task_id"]
            st.success(f"Задача создана: `{task_id}`")

            # Ожидание результата с отображением прогресса
            status_placeholder = st.empty()
            result_placeholder = st.empty()

            for _ in range(60):  # Ожидание до 30 секунд
                time.sleep(0.5)
                status_data = client.get_task_status(task_id)
                status = status_data["status"]
                status_placeholder.info(f"Статус: **{status}**")

                if status == "completed":
                    result = status_data.get("result", {})
                    result_placeholder.success("✅ Задача выполнена!")
                    st.markdown("### Результат:")
                    st.markdown(result.get("content", str(result)))
                    break
                elif status == "failed":
                    result_placeholder.error(f"❌ Ошибка: {status_data.get('error', 'Unknown')}")
                    break
        except Exception as e:
            st.error(f"Ошибка при создании задачи: {e}")
```

---

## 6. CLI (Command-Line Interface)

### 6.1. Структура Команд

```
vagus/
├── __main__.py                # Точка входа: python -m vagus
└── layer3/
    └── cli/
        ├── __init__.py
        ├── app.py             # Корневое Typer-приложение
        ├── commands/
        │   ├── task.py        # Группа команд: vagus task
        │   ├── agent.py       # Группа команд: vagus agent
        │   └── admin.py       # Группа команд: vagus admin
        └── utils/
            ├── config.py      # Управление ~/.vagus/config.json
            ├── api_client.py  # HTTP-клиент для CLI
            └── output.py      # Форматирование вывода (rich)
```

### 6.2. Реализация CLI

```python
# src/vagus/layer3/cli/app.py

import typer
from .commands import task, agent, admin

app = typer.Typer(
    name="vagus",
    help="🤖 Vagus Asistent — многослойная агентная AI-система",
    add_completion=True,
)

app.add_typer(task.app, name="task", help="Управление задачами")
app.add_typer(agent.app, name="agent", help="Информация об агентах")
app.add_typer(admin.app, name="admin", help="Администрирование системы")


@app.command()
def login(
    api_url: str = typer.Option("http://localhost:8000", help="URL API сервера"),
    api_key: str = typer.Option(..., prompt=True, hide_input=True, help="API-ключ"),
):
    """Аутентификация и сохранение учётных данных."""
    from .utils.config import save_config
    save_config({"api_url": api_url, "api_key": api_key})
    typer.echo("✅ Учётные данные сохранены.")


if __name__ == "__main__":
    app()
```

```python
# src/vagus/layer3/cli/commands/task.py

import typer
from rich.console import Console
from rich.table import Table
from ..utils.api_client import CLIApiClient

app = typer.Typer()
console = Console()


@app.command("create")
def create_task(
    prompt: str = typer.Argument(..., help="Запрос для выполнения"),
    task_type: str = typer.Option("default", "--type", "-t", help="Тип задачи"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Ожидать завершения"),
    stream: bool = typer.Option(False, "--stream", help="Стримить результат"),
):
    """Создать и выполнить новую задачу."""
    import asyncio
    client = CLIApiClient()

    with console.status("[bold green]Создание задачи..."):
        response = client.create_task(prompt=prompt, task_type=task_type)
        task_id = response["task_id"]

    console.print(f"[green]✅ Задача создана:[/green] [bold]{task_id}[/bold]")

    if wait:
        import time
        console.print("[yellow]⏳ Ожидание результата...[/yellow]")
        for _ in range(120):
            time.sleep(0.5)
            status_data = client.get_task_status(task_id)
            status = status_data["status"]

            if status == "completed":
                console.print("\n[bold green]✅ Задача выполнена![/bold green]")
                result = status_data.get("result", {})
                console.print(result.get("content", str(result)))
                break
            elif status == "failed":
                console.print(f"\n[bold red]❌ Ошибка:[/bold red] {status_data.get('error')}")
                raise typer.Exit(code=1)


@app.command("status")
def get_status(task_id: str = typer.Argument(..., help="ID задачи")):
    """Получить статус задачи."""
    client = CLIApiClient()
    data = client.get_task_status(task_id)

    table = Table(title=f"Статус задачи {task_id}")
    table.add_column("Поле", style="cyan")
    table.add_column("Значение", style="white")

    for key, value in data.items():
        table.add_row(str(key), str(value))

    console.print(table)


@app.command("list")
def list_tasks(limit: int = typer.Option(10, "--limit", "-n", help="Количество задач")):
    """Показать список последних задач."""
    client = CLIApiClient()
    tasks = client.list_tasks(limit=limit)

    table = Table(title="Список задач")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Статус", style="green")
    table.add_column("Создана", style="white")

    for task in tasks:
        table.add_row(task["task_id"], task["status"], task["created_at"])

    console.print(table)
```

---

## 7. Channel Gateway (Chat Bots)

### 7.1. Архитектура Channel Gateway

Channel Gateway — это отдельный, независимо запускаемый сервис, который выступает в роли адаптера между чат-платформами и REST API Vagus Asistent. Он не содержит бизнес-логики и является чисто транспортным слоем.

```
src/vagus/layer3/channels/
├── __init__.py
├── gateway.py              # Основной класс ChannelGateway
├── telegram/
│   ├── __init__.py
│   ├── bot.py              # aiogram-приложение
│   ├── handlers.py         # Обработчики сообщений
│   ├── middleware.py       # Middleware для аутентификации пользователей
│   └── keyboards.py        # Inline-клавиатуры
└── discord/
    ├── __init__.py
    └── bot.py              # nextcord-приложение
```

### 7.2. Telegram Bot (aiogram 3.x)

```python
# src/vagus/layer3/channels/telegram/bot.py

import asyncio
import logging
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from .middleware import UserAuthMiddleware
from ..gateway import ChannelGateway

router = Router()
gateway: ChannelGateway = None  # Инициализируется при старте


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start."""
    await message.answer(
        "👋 Привет! Я Vagus Asistent — ваш AI-помощник.\n\n"
        "Просто напишите мне запрос, и я выполню его с помощью AI-агентов.\n\n"
        "Команды:\n"
        "/status — статус последней задачи\n"
        "/help — справка"
    )


@router.message()
async def handle_message(message: Message):
    """Основной обработчик текстовых сообщений."""
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    prompt = message.text

    # Отправка индикатора "печатает..."
    await message.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Создание задачи через Gateway
    thinking_msg = await message.answer("🤔 Обрабатываю запрос...")

    try:
        result = await gateway.process_message(
            user_id=user_id,
            chat_id=chat_id,
            prompt=prompt,
        )
        await thinking_msg.edit_text(f"✅ {result}")
    except Exception as e:
        await thinking_msg.edit_text(f"❌ Произошла ошибка: {e}")


async def start_telegram_bot(token: str, api_url: str, api_key: str):
    """Запуск Telegram-бота."""
    global gateway
    gateway = ChannelGateway(api_url=api_url, api_key=api_key)

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.message.middleware(UserAuthMiddleware())
    dp.include_router(router)

    logging.info("Starting Telegram bot...")
    await dp.start_polling(bot)
```

```python
# src/vagus/layer3/channels/gateway.py

import asyncio
import httpx
from typing import Any


class ChannelGateway:
    """
    Шлюз между чат-каналами и REST API Vagus Asistent.
    Транслирует сообщения из чатов в вызовы API и возвращает результаты.
    """

    def __init__(self, api_url: str, api_key: str, timeout: int = 120):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def process_message(
        self,
        user_id: str,
        chat_id: str,
        prompt: str,
        task_type: str = "default",
    ) -> str:
        """
        Создаёт задачу через API и ожидает её выполнения.
        Возвращает строку с результатом.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # 1. Создание задачи
            create_resp = await client.post(
                f"{self.api_url}/api/v1/tasks",
                json={
                    "prompt": prompt,
                    "task_type": task_type,
                    "metadata": {"user_id": user_id, "chat_id": chat_id},
                },
                headers=self._headers,
            )
            create_resp.raise_for_status()
            task_data = create_resp.json()
            task_id = task_data["task_id"]

            # 2. Ожидание результата
            for _ in range(self.timeout * 2):  # Проверяем каждые 0.5 секунды
                await asyncio.sleep(0.5)
                status_resp = await client.get(
                    f"{self.api_url}/api/v1/tasks/{task_id}",
                    headers=self._headers,
                )
                status_resp.raise_for_status()
                status_data = status_resp.json()

                if status_data["status"] == "completed":
                    result = status_data.get("result", {})
                    return result.get("content", str(result))
                elif status_data["status"] == "failed":
                    raise RuntimeError(status_data.get("error", "Task failed"))

        raise TimeoutError(f"Task {task_id} did not complete within {self.timeout}s")
```

---

## 8. Интеграция со Слоем 2

### 8.1. Принцип Единственного Экземпляра

`TaskOrchestrator` создаётся **один раз** при запуске FastAPI-приложения и хранится в `app.state`. Это критически важно, так как оркестратор управляет состоянием задач и агентов. Создание нескольких экземпляров привело бы к потере состояния и непредсказуемому поведению.

### 8.2. Dependency Injection

FastAPI предоставляет элегантный механизм внедрения зависимостей, который позволяет эндпоинтам получать доступ к `TaskOrchestrator` без создания глобальных переменных.

```python
# src/vagus/layer3/api/dependencies.py

from fastapi import Request, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from vagus.layer2.orchestrator import TaskOrchestrator
from .auth import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_orchestrator(request: Request) -> TaskOrchestrator:
    """Зависимость: получить экземпляр TaskOrchestrator из состояния приложения."""
    return request.app.state.orchestrator


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Зависимость: декодировать JWT и вернуть данные пользователя."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    return payload
```

### 8.3. Схема Взаимодействия

Ниже представлена полная схема взаимодействия от получения HTTP-запроса до возврата результата.

```
HTTP POST /api/v1/tasks
        │
        ▼
┌───────────────────────────────┐
│  FastAPI Middleware            │
│  - CORS                       │
│  - Rate Limiting              │
│  - Request Logging            │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│  JWT Authentication           │
│  get_current_user(token)      │
│  → Проверка подписи токена    │
│  → Извлечение user_id, roles  │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│  Pydantic Validation          │
│  TaskCreateRequest(...)       │
│  → Проверка типов данных      │
│  → Валидация длины prompt     │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│  create_task() endpoint       │
│  task_id = uuid4()            │
│  asyncio.create_task(         │
│    orchestrator.execute_task  │
│  )                            │
│  → Немедленный ответ 201      │
└───────────────┬───────────────┘
                │ (фоновая задача)
                ▼
┌───────────────────────────────┐
│  TaskOrchestrator (Слой 2)    │
│  execute_task(id, prompt, ...) │
│  → _select_agent(task_type)   │
│  → agent.process(task)        │
└───────────────┬───────────────┘
                │
                ▼
┌───────────────────────────────┐
│  ResearcherAgent / CoderAgent │
│  → skill_system.use_skill()   │
│  → llm_router.route_request() │
└───────────────────────────────┘
```

---

## 9. Безопасность: Аутентификация и Авторизация

### 9.1. JWT-аутентификация

```python
# src/vagus/layer3/api/auth.py

from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = "your-secret-key-from-env"  # Загружается из .env
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(data: dict) -> str:
    """Создаёт JWT access token с коротким сроком жизни."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Создаёт JWT refresh token с длительным сроком жизни."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """Декодирует и валидирует JWT токен. Возвращает None при ошибке."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
```

### 9.2. Rate Limiting

Для защиты API от злоупотреблений необходимо реализовать ограничение частоты запросов. Это реализуется через FastAPI Middleware.

```python
# src/vagus/layer3/api/middleware/rate_limit.py

import time
from collections import defaultdict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Простой in-memory rate limiter.
    В production следует использовать Redis.
    """

    def __init__(self, app, max_requests: int = 60, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host
        now = time.monotonic()
        window_start = now - self.window_seconds

        # Очистка устаревших записей
        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if t > window_start
        ]

        if len(self._requests[client_ip]) >= self.max_requests:
            return Response(
                content='{"detail": "Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
            )

        self._requests[client_ip].append(now)
        return await call_next(request)
```

---

## 10. Структура Файлов Проекта

```
src/vagus/
├── layer0/                    # ✅ Готов
├── layer1/                    # ✅ Готов
├── layer2/                    # 🚧 В процессе
└── layer3/                    # 📋 Планируется
    ├── __init__.py
    ├── api/                   # REST API (FastAPI)
    │   ├── __init__.py
    │   ├── main.py            # Точка входа FastAPI
    │   ├── models.py          # Pydantic-модели
    │   ├── dependencies.py    # FastAPI Depends
    │   ├── auth.py            # JWT-аутентификация
    │   ├── middleware/
    │   │   ├── __init__.py
    │   │   ├── rate_limit.py  # Rate limiting
    │   │   └── logging.py     # Request logging
    │   └── routers/
    │       ├── __init__.py
    │       ├── auth.py        # /auth/token, /auth/refresh
    │       ├── tasks.py       # /tasks, /tasks/{id}
    │       ├── agents.py      # /agents
    │       └── status.py      # /status
    ├── cli/                   # CLI (Typer)
    │   ├── __init__.py
    │   ├── app.py             # Корневое Typer-приложение
    │   ├── commands/
    │   │   ├── task.py        # vagus task create/status/list
    │   │   ├── agent.py       # vagus agent list
    │   │   └── admin.py       # vagus admin status/user
    │   └── utils/
    │       ├── config.py      # ~/.vagus/config.json
    │       ├── api_client.py  # HTTP-клиент для CLI
    │       └── output.py      # rich-форматирование
    └── channels/              # Channel Gateway (Chat Bots)
        ├── __init__.py
        ├── gateway.py         # ChannelGateway (общий клиент API)
        ├── telegram/
        │   ├── __init__.py
        │   ├── bot.py         # aiogram Dispatcher
        │   ├── handlers.py    # Обработчики сообщений
        │   └── middleware.py  # UserAuthMiddleware
        └── discord/
            ├── __init__.py
            └── bot.py         # nextcord Client

dashboard/                     # Web Dashboard (Streamlit)
├── main.py                    # Точка входа
├── pages/
│   ├── 1_Tasks.py
│   ├── 2_Monitoring.py
│   ├── 3_Agents.py
│   └── 4_Settings.py
└── utils/
    ├── api_client.py
    ├── auth.py
    └── charts.py
```

---

## 11. План Реализации

### 11.1. Этапы и Оценка Сложности

| Этап | Компонент                       | Сложность | Длительность | Зависимости     |
| :--- | :------------------------------ | :-------- | :----------- | :-------------- |
| 1    | Ядро REST API (FastAPI)         | Средняя   | 3–4 дня      | Слой 2 (скелет) |
| 2    | JWT-аутентификация              | Средняя   | 1–2 дня      | Этап 1          |
| 3    | CLI (Typer)                     | Низкая    | 1–2 дня      | Этап 1          |
| 4    | WebSocket стриминг              | Средняя   | 2–3 дня      | Этап 2          |
| 5    | Web Dashboard (Streamlit)       | Средняя   | 3–5 дней     | Этап 2, 4       |
| 6    | Telegram Bot (aiogram)          | Высокая   | 3–4 дня      | Этап 2          |
| 7    | Discord Bot (nextcord)          | Средняя   | 2–3 дня      | Этап 6          |
| 8    | Rate Limiting и Middleware      | Низкая    | 1 день       | Этап 1          |
| 9    | Интеграционные тесты            | Средняя   | 2–3 дня      | Этапы 1–6       |

**Общая оценка:** 18–27 дней при последовательной реализации. При параллельной работе (например, CLI + Dashboard одновременно) — 12–18 дней.

### 11.2. Рекомендации по Тестированию

**Unit-тесты (pytest)** должны покрывать каждый компонент в изоляции. Для FastAPI используется `TestClient`, который позволяет тестировать эндпоинты без запуска реального сервера. `TaskOrchestrator` при этом мокируется с помощью `unittest.mock`.

```python
# tests/layer3/test_tasks_api.py

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from vagus.layer3.api.main import app

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def mock_orchestrator():
    with patch("vagus.layer3.api.main.TaskOrchestrator") as mock:
        mock_instance = AsyncMock()
        mock_instance.execute_task.return_value = {
            "content": "Тестовый результат",
            "metadata": {}
        }
        mock.return_value = mock_instance
        yield mock_instance

def test_create_task_success(client, mock_orchestrator, auth_headers):
    response = client.post(
        "/api/v1/tasks",
        json={"prompt": "Тестовый запрос", "task_type": "default"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "pending"

def test_create_task_unauthorized(client):
    response = client.post(
        "/api/v1/tasks",
        json={"prompt": "Тестовый запрос"},
    )
    assert response.status_code == 401
```

**Интеграционные тесты** проверяют полную цепочку взаимодействий: от HTTP-запроса через API до вызова `TaskOrchestrator`. Они запускаются с реальными экземплярами компонентов, но с замоканными провайдерами LLM.

**Нагрузочное тестирование** рекомендуется проводить с помощью `locust` после завершения основных этапов. Цель — убедиться, что API выдерживает не менее 100 одновременных запросов без деградации производительности.

---

## 12. Подводные Камни и Решения

| Проблема                                  | Решение                                                                                   |
| :---------------------------------------- | :---------------------------------------------------------------------------------------- |
| **Блокировка event loop** при долгих задачах | Использование `asyncio.create_task()` для фоновых задач; никогда не `await` долгие операции в эндпоинте |
| **Потеря состояния задач** при перезапуске | Хранение `_task_store` в Redis или SQLite вместо in-memory dict                           |
| **Таймаут WebSocket** при долгих задачах  | Реализация heartbeat (пинг каждые 30 секунд) для поддержания соединения                  |
| **Утечка памяти** в `_task_store`         | Автоматическая очистка завершённых задач через TTL (например, через 1 час)                |
| **Telegram rate limit** при стриминге     | Редактирование одного сообщения вместо отправки новых; пакетирование обновлений           |
| **CORS-ошибки** при разработке            | Настройка `CORSMiddleware` с явным указанием разрешённых источников                       |
| **JWT-токен в WebSocket URL**             | Передача токена через query-параметр (`?token=...`) или через первое сообщение WebSocket  |
| **Параллельные запросы от одного пользователя** | Rate limiting на уровне user_id (не только IP) для предотвращения злоупотреблений  |

---

## 13. Промпты для Kursor AI Mob

Ниже приведены готовые промпты для последовательной реализации Слоя 3 с помощью Kursor AI Mob. Каждый промпт является самодостаточным и может быть выполнен независимо.

---

### 🔵 ПРОМПТ 1: Создание структуры Слоя 3

```
Создай структуру папок и файлов для Слоя 3 (Интерфейсы) проекта Vagus Asistent.

Структура:
src/vagus/layer3/
├── __init__.py
├── api/
│   ├── __init__.py
│   ├── main.py
│   ├── models.py
│   ├── dependencies.py
│   ├── auth.py
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── rate_limit.py
│   └── routers/
│       ├── __init__.py
│       ├── auth.py
│       ├── tasks.py
│       ├── agents.py
│       └── status.py
├── cli/
│   ├── __init__.py
│   ├── app.py
│   └── commands/
│       ├── __init__.py
│       └── task.py
└── channels/
    ├── __init__.py
    └── gateway.py

В каждый файл добавь заглушку с docstring, описывающим назначение файла.
Используй Python 3.11+, следуй стилю существующего кода в src/vagus/.
```

---

### 🔵 ПРОМПТ 2: REST API — Pydantic-модели и FastAPI main.py

```
Реализуй ядро REST API для Vagus Asistent.

Файл: src/vagus/layer3/api/models.py
Создай Pydantic-модели:
- TaskStatus (Enum: pending, in_progress, completed, failed)
- TaskCreateRequest (prompt: str, task_type: str = "default", metadata: Optional[Dict])
- TaskCreateResponse (task_id: str, status: TaskStatus, status_endpoint: str, stream_endpoint: str, created_at: datetime)
- TaskStatusResponse (task_id, status, result, error, metadata, created_at, updated_at)
- AgentInfoResponse (name, description, task_types: List[str], is_available: bool)
- SystemStatusResponse (layer1_stats: Dict, layer2_agents_count: int, active_tasks_count: int, uptime_seconds: float)

Файл: src/vagus/layer3/api/main.py
Создай FastAPI-приложение с:
- lifespan context manager, который инициализирует LLMRouter (из vagus.layer1) и TaskOrchestrator (из vagus.layer2) при старте
- CORSMiddleware для http://localhost:8501
- Подключением роутеров из routers/
- Документацией OpenAPI

Используй asyncio, Pydantic v2, Python 3.11+.
```

---

### 🔵 ПРОМПТ 3: REST API — Роутер задач (tasks.py)

```
Реализуй роутер задач для Vagus Asistent REST API.

Файл: src/vagus/layer3/api/routers/tasks.py

Реализуй:
1. POST /tasks — создание задачи
   - Принимает TaskCreateRequest
   - Генерирует task_id = str(uuid4())
   - Запускает orchestrator.execute_task() через asyncio.create_task() (не блокирует)
   - Сохраняет состояние задачи в _task_store (dict)
   - Возвращает TaskCreateResponse с task_id и URL-ами для статуса и стриминга

2. GET /tasks/{task_id} — статус задачи
   - Возвращает TaskStatusResponse из _task_store
   - 404 если задача не найдена

3. WebSocket /ws/tasks/{task_id} — стриминг результата
   - Принимает WebSocket-соединение
   - Каждые 0.5 секунды проверяет статус задачи в _task_store
   - Отправляет {"content": null, "done": false} пока задача выполняется
   - Отправляет {"content": "...", "done": true} при завершении
   - Отправляет {"error": "...", "done": true} при ошибке

Используй зависимости get_orchestrator и get_current_user из dependencies.py.
```

---

### 🔵 ПРОМПТ 4: JWT-аутентификация

```
Реализуй JWT-аутентификацию для Vagus Asistent REST API.

Файл: src/vagus/layer3/api/auth.py
Функции:
- create_access_token(data: dict) -> str (срок: 15 минут)
- create_refresh_token(data: dict) -> str (срок: 7 дней)
- decode_access_token(token: str) -> Optional[dict]
- verify_password(plain: str, hashed: str) -> bool
- get_password_hash(password: str) -> str

Используй: python-jose[cryptography], passlib[bcrypt]
SECRET_KEY загружается из переменной окружения VAGUS_SECRET_KEY.

Файл: src/vagus/layer3/api/routers/auth.py
Эндпоинты:
- POST /auth/token — принимает username/password (OAuth2PasswordRequestForm), возвращает access_token и refresh_token
- POST /auth/refresh — принимает refresh_token, возвращает новый access_token

Файл: src/vagus/layer3/api/dependencies.py
Функции:
- get_orchestrator(request: Request) -> TaskOrchestrator
- get_current_user(token: str = Depends(oauth2_scheme)) -> dict
```

---

### 🔵 ПРОМПТ 5: CLI на Typer

```
Реализуй CLI для Vagus Asistent на Typer.

Файл: src/vagus/layer3/cli/app.py
- Корневое Typer-приложение с именем "vagus"
- Команда "login" для сохранения API-ключа в ~/.vagus/config.json
- Подключение групп команд: task, agent

Файл: src/vagus/layer3/cli/commands/task.py
Команды:
- "create" <prompt> [--type default] [--wait/--no-wait]
  Создаёт задачу через HTTP POST /api/v1/tasks.
  Если --wait, опрашивает статус каждые 0.5 секунды и выводит результат.
  Использует rich для красивого вывода.

- "status" <task_id>
  Выводит статус задачи в виде таблицы (rich.Table).

- "list" [--limit 10]
  Выводит список последних задач.

Файл: src/vagus/layer3/cli/utils/api_client.py
Класс CLIApiClient с методами create_task, get_task_status, list_tasks.
Читает api_url и api_key из ~/.vagus/config.json.

Зависимости: typer, rich, httpx.
```

---

### 🔵 ПРОМПТ 6: Telegram Bot на aiogram 3

```
Реализуй Telegram-бота для Vagus Asistent на aiogram 3.x.

Файл: src/vagus/layer3/channels/gateway.py
Класс ChannelGateway:
- __init__(api_url: str, api_key: str, timeout: int = 120)
- async process_message(user_id: str, chat_id: str, prompt: str, task_type: str = "default") -> str
  Создаёт задачу через POST /api/v1/tasks, ожидает завершения, возвращает строку с результатом.
  Использует httpx.AsyncClient.

Файл: src/vagus/layer3/channels/telegram/bot.py
- Настройка aiogram Bot и Dispatcher
- Обработчик /start с приветственным сообщением
- Обработчик текстовых сообщений:
  1. Отправляет "🤔 Обрабатываю запрос..."
  2. Вызывает gateway.process_message()
  3. Редактирует сообщение с результатом
  4. Обрабатывает ошибки и таймауты
- Функция start_telegram_bot(token: str, api_url: str, api_key: str)

Токен бота загружается из переменной окружения TELEGRAM_BOT_TOKEN.
Зависимости: aiogram>=3.0, httpx.
```

---

### 🔵 ПРОМПТ 7: Web Dashboard на Streamlit

```
Реализуй Web Dashboard для Vagus Asistent на Streamlit.

Файл: dashboard/utils/api_client.py
Класс VagusAPIClient:
- login(username, password) -> bool — POST /auth/token, сохраняет JWT в st.session_state
- create_task(prompt, task_type) -> dict
- get_task_status(task_id) -> dict
- get_system_status() -> dict
- get_agents() -> list

Файл: dashboard/pages/1_Tasks.py
- Форма: text_area для промпта, selectbox для типа задачи, кнопка "Запустить"
- После создания задачи: цикл опроса статуса каждые 0.5 секунды
- Отображение результата через st.markdown()
- Обработка ошибок через st.error()

Файл: dashboard/pages/2_Monitoring.py
- Вызов get_system_status() для получения метрик
- Отображение метрик через st.metric()
- Графики через st.line_chart() или plotly

Файл: dashboard/main.py
- Конфигурация страниц, проверка аутентификации
- Форма входа (username/password) если не аутентифицирован

Зависимости: streamlit, httpx, plotly.
```

---

### 🔵 ПРОМПТ 8: Тесты для REST API

```
Напиши unit-тесты для REST API Vagus Asistent.

Файл: tests/layer3/test_tasks_api.py

Тесты:
1. test_create_task_success — POST /tasks с валидным JWT возвращает 201 и task_id
2. test_create_task_unauthorized — POST /tasks без JWT возвращает 401
3. test_create_task_empty_prompt — POST /tasks с пустым prompt возвращает 422
4. test_get_task_status_found — GET /tasks/{id} возвращает корректный статус
5. test_get_task_status_not_found — GET /tasks/{несуществующий_id} возвращает 404
6. test_rate_limit — 61 запрос подряд, последний возвращает 429

Используй:
- pytest, pytest-asyncio
- fastapi.testclient.TestClient
- unittest.mock.AsyncMock для мокирования TaskOrchestrator
- Фикстуры: client (TestClient), auth_headers (JWT-заголовок), mock_orchestrator
```

---

## 📌 Итоговая Сводка

| Компонент          | Технология         | Статус     | Приоритет |
| :----------------- | :----------------- | :--------- | :-------- |
| REST API Gateway   | FastAPI + Pydantic | 📋 Планируется | Высокий   |
| JWT Auth           | python-jose + passlib | 📋 Планируется | Высокий   |
| Web Dashboard      | Streamlit          | 📋 Планируется | Средний   |
| CLI                | Typer + rich       | 📋 Планируется | Средний   |
| Telegram Bot       | aiogram 3.x        | 📋 Планируется | Средний   |
| Discord Bot        | nextcord           | 📋 Планируется | Низкий    |
| Rate Limiting      | FastAPI Middleware  | 📋 Планируется | Высокий   |
| WebSocket Streaming | FastAPI WebSocket  | 📋 Планируется | Средний   |

---

**✅ ДИЗАЙН-ДОКУМЕНТ ГОТОВ К ИСПОЛЬЗОВАНИЮ В KURSOR AI MOB**
