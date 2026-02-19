"""
Pydantic-модели запросов и ответов REST API.
Строгая типизация всех входящих и исходящих данных.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
        description="Основной запрос или команда для выполнения агентом",
    )
    task_type: str = Field(
        default="default",
        description="Тип задачи: 'research', 'code', 'analysis', 'default'",
    )
    stream: bool = Field(
        default=False,
        description="Если True, результат будет доступен через WebSocket",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Дополнительные метаданные",
    )


class TokenRequest(BaseModel):
    """Запрос на обновление токена."""

    refresh_token: str = Field(..., description="Refresh-токен для получения нового access_token")


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


class TaskListResponse(BaseModel):
    """Список задач."""

    tasks: List[TaskStatusResponse]
    total: int


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


class TokenResponse(BaseModel):
    """Ответ с JWT-токенами."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class WebSocketStreamChunk(BaseModel):
    """Один чанк стриминга через WebSocket."""

    content: Optional[str] = None
    done: bool = False
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Стандартный ответ об ошибке."""

    detail: str
