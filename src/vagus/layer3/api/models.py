"""
Pydantic-модели запросов и ответов REST API.
"""

from datetime import datetime, timezone
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
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="Основной запрос для выполнения агентом",
    )
    task_type: str = Field(
        default="default",
        description="Тип задачи: 'research', 'code', 'analysis', 'default'",
    )
    stream: bool = Field(
        default=False,
        description="Если True, результат доступен через WebSocket",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Дополнительные метаданные",
    )


class TokenRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


# --- Ответы ---


class TaskCreateResponse(BaseModel):
    task_id: str = Field(..., description="UUID задачи")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    status_endpoint: str = Field(..., description="URL для статуса")
    stream_endpoint: str = Field(..., description="WebSocket URL")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class TaskListItem(BaseModel):
    task_id: str
    status: TaskStatus
    created_at: datetime


class AgentInfoResponse(BaseModel):
    name: str
    description: str
    task_types: List[str]
    is_available: bool


class SystemStatusResponse(BaseModel):
    layer1_stats: Dict[str, Any] = Field(default_factory=dict)
    layer2_agents_count: int = 0
    active_tasks_count: int = 0
    uptime_seconds: float = 0.0


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class WebSocketStreamChunk(BaseModel):
    content: Optional[str] = None
    done: bool = False
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class WebSocketAuditLogEntry(BaseModel):
    id: int
    event_type: str
    user_id: Optional[str] = None
    task_id: Optional[str] = None
    timestamp: datetime
    message_size_bytes: Optional[int] = None
    message_type: Optional[str] = None
    close_code: Optional[int] = None
    reason: Optional[str] = None
    duration_seconds: Optional[float] = None


class ErrorResponse(BaseModel):
    detail: str
