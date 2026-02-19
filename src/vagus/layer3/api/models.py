"""
Pydantic модели для API запросов и ответов.
Схемы валидации входных данных и сериализации результатов.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Состояния задачи."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskCreateRequest(BaseModel):
    """Запрос на создание задачи."""

    prompt: str = Field(..., description="Текст запроса/prompt для задачи")
    task_type: str = Field(default="default", description="Тип задачи")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Дополнительные метаданные")


class TaskCreateResponse(BaseModel):
    """Ответ при создании задачи."""

    task_id: str = Field(..., description="Идентификатор созданной задачи")
    status: TaskStatus = Field(..., description="Текущий статус задачи")
    status_endpoint: str = Field(..., description="URL для проверки статуса")
    stream_endpoint: str = Field(..., description="URL для стриминга результата")
    created_at: datetime = Field(..., description="Время создания")


class TaskStatusResponse(BaseModel):
    """Ответ со статусом задачи."""

    task_id: str = Field(..., description="Идентификатор задачи")
    status: TaskStatus = Field(..., description="Текущий статус")
    result: Optional[Any] = Field(default=None, description="Результат выполнения")
    error: Optional[str] = Field(default=None, description="Сообщение об ошибке при failure")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Метаданные задачи")
    created_at: datetime = Field(..., description="Время создания")
    updated_at: datetime = Field(..., description="Время последнего обновления")


class AgentInfoResponse(BaseModel):
    """Информация об агенте."""

    name: str = Field(..., description="Имя агента")
    description: str = Field(..., description="Описание агента")
    task_types: List[str] = Field(default_factory=list, description="Поддерживаемые типы задач")
    is_available: bool = Field(..., description="Доступность агента")


class SystemStatusResponse(BaseModel):
    """Статус системы."""

    layer1_stats: Dict[str, Any] = Field(default_factory=dict, description="Статистика Layer 1 (LLM Router)")
    layer2_agents_count: int = Field(..., description="Количество зарегистрированных агентов")
    active_tasks_count: int = Field(..., description="Количество активных задач")
    uptime_seconds: float = Field(..., description="Время работы в секундах")
