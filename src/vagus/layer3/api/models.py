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
    goal: Optional[str] = Field(
        default=None,
        max_length=10000,
        description="Целевой результат для сложных многошаговых задач",
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


class TaskResponse(BaseModel):
    """Расширенный ответ задачи с plan, quality_score, reflection_count."""

    task_id: str
    status: TaskStatus
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    plan: Optional[Any] = Field(
        default=None,
        description="Сгенерированный план выполнения",
    )
    quality_score: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description="Итоговая оценка качества",
    )
    reflection_count: Optional[int] = Field(
        default=None,
        ge=0,
        description="Количество итераций рефлексии",
    )


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


class AuditTrailLogEntry(BaseModel):
    id: int
    timestamp: datetime
    user_id: Optional[str] = None
    action: str
    resource: str
    details: Any
    ip_address: Optional[str] = None


class DeadLetterQueueEntryResponse(BaseModel):
    id: int
    task_id: str
    agent_type: str
    error_message: str
    stack_trace: str
    timestamp: datetime
    retry_count: int
    status: str
    manual_fix_note: Optional[str] = None
    task_payload: Optional[Dict[str, Any]] = None


class DeadLetterQueueManualFixRequest(BaseModel):
    note: str = Field(..., min_length=1, max_length=5000)


class DeadLetterQueueRetryRequest(BaseModel):
    prompt: Optional[str] = None
    task_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class DeadLetterQueueRetryResponse(BaseModel):
    task_id: str
    retry_task_id: str
    retry_count: int
    success: bool
    result: Any = None


class CircuitBreakerStatsResponse(BaseModel):
    provider_id: str
    state: str
    failure_count: int
    last_failure_time: Optional[str] = None
    success_rate: float = 0.0
    recovery_timeout: int = 0
    failure_threshold: int = 0
    total_success_count: int = 0
    total_failure_count: int = 0


class CircuitBreakerHistoryEntry(BaseModel):
    timestamp: str
    states: Dict[str, str] = Field(default_factory=dict)


class CircuitBreakersResponse(BaseModel):
    breakers: List[CircuitBreakerStatsResponse] = Field(default_factory=list)
    history: List[CircuitBreakerHistoryEntry] = Field(default_factory=list)


class CircuitBreakerResetResponse(BaseModel):
    provider_id: str
    status: str = Field(default="reset")


class ErrorAnalyticsResponse(BaseModel):
    """Aggregated error analytics snapshot payload."""

    error_rate_by_type: Dict[str, Any] = Field(default_factory=dict)
    top_error_sources: List[Dict[str, Any]] = Field(default_factory=list)
    correlation: Dict[str, Any] = Field(default_factory=dict)
    recent_events: List[Dict[str, Any]] = Field(default_factory=list)


class MemoryStatsResponse(BaseModel):
    """Memory profiler runtime payload."""

    current: Dict[str, Any] = Field(default_factory=dict)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    history_size: int = 0
    leak_policy: Dict[str, Any] = Field(default_factory=dict)
    monitoring_active: bool = False


class PluginInfoResponse(BaseModel):
    """Public plugin metadata for dashboard/API clients."""

    name: str = Field(..., description="Уникальное имя плагина", examples=["test-plugin"])
    version: str = Field(..., description="Версия установленного плагина", examples=["1.0.0"])
    status: str = Field(..., description="Текущее состояние плагина", examples=["ENABLED"])
    enabled: bool = Field(..., description="Флаг включения плагина")
    author: str = Field(..., description="Автор плагина")
    description: str = Field(..., description="Краткое описание")
    source: Optional[str] = Field(default=None, description="Исходный install source")
    path: Optional[str] = Field(default=None, description="Локальный путь установки")
    installed_at: Optional[str] = Field(default=None, description="ISO-время установки")
    load_error: Optional[str] = Field(default=None, description="Ошибка загрузки, если есть")


class PluginInstallRequest(BaseModel):
    source: str = Field(
        ...,
        min_length=1,
        description="Локальный путь, URL или marketplace ID",
        examples=["./plugins/my-plugin"],
    )
    version: Optional[str] = Field(
        default=None,
        description="Опциональная версия (для git ref/marketplace)",
        examples=["1.2.0"],
    )


class PluginConfigResponse(BaseModel):
    settings: Dict[str, Any] = Field(default_factory=dict, description="Публичные настройки плагина")
    secrets: Dict[str, Any] = Field(default_factory=dict, description="Секреты плагина")
    ui_schema: Dict[str, Any] = Field(default_factory=dict, description="UI schema для dashboard-форм")


class PluginConfigUpdateRequest(BaseModel):
    settings: Optional[Dict[str, Any]] = Field(default=None, description="Обновление settings")
    secrets: Optional[Dict[str, Any]] = Field(default=None, description="Обновление secrets")
    ui_schema: Optional[Dict[str, Any]] = Field(default=None, description="Обновление ui_schema")


class PluginDeleteResponse(BaseModel):
    plugin_name: str
    status: str = Field(default="deleted")


class MarketplacePluginSummary(BaseModel):
    plugin_id: str = Field(..., examples=["demo-plugin"])
    name: str
    description: str = ""
    category: str = "general"
    author: str = "unknown"
    latest_version: Optional[str] = None
    download_url: Optional[str] = None
    avg_rating: float = 0.0
    review_count: int = 0


class MarketplacePluginVersion(BaseModel):
    version: str
    changelog: str = ""
    download_url: Optional[str] = None
    created_at: Optional[str] = None


class MarketplacePluginReview(BaseModel):
    rating: float
    review: Optional[str] = None
    created_at: Optional[str] = None


class MarketplacePluginDetailResponse(MarketplacePluginSummary):
    metadata: Dict[str, Any] = Field(default_factory=dict)
    versions: List[MarketplacePluginVersion] = Field(default_factory=list)
    reviews: List[MarketplacePluginReview] = Field(default_factory=list)


class MarketplaceInstallRequest(BaseModel):
    version: Optional[str] = Field(default=None, description="Целевая версия marketplace-плагина")


class PluginDependencyResponse(BaseModel):
    plugin_name: str
    dependencies: List[str] = Field(default_factory=list)
    install_order: List[str] = Field(default_factory=list)
    graph: Dict[str, List[str]] = Field(default_factory=dict)
    edges: List[Dict[str, str]] = Field(default_factory=list)
    conflicts: Dict[str, List[str]] = Field(default_factory=dict)
    missing_dependencies: List[str] = Field(default_factory=list)


class PluginStatisticsResponse(BaseModel):
    summary: Dict[str, Any] = Field(default_factory=dict)
    popularity: List[Dict[str, Any]] = Field(default_factory=list)
    trending: List[MarketplacePluginSummary] = Field(default_factory=list)


class PluginDependencyHealthItem(BaseModel):
    dependency_name: str
    required_spec: str = ""
    installed_version: Optional[str] = None
    available: bool = False
    compatible: bool = False
    status: str = "unknown"
    recommendation: str = ""


class PluginDependencyResolveRequest(BaseModel):
    strategy: str = Field(default="prefer-installed")
    dry_run: bool = Field(default=False)
    pin_versions: bool = Field(default=True)
    export_lock: bool = Field(default=True)


class PluginDependencyUpdateRequest(BaseModel):
    updates: Dict[str, str] = Field(default_factory=dict)
    pin_versions: bool = Field(default=False)
    dry_run: bool = Field(default=False)
    export_lock: bool = Field(default=True)
    import_lock_content: Optional[str] = Field(default=None)


class PluginDependencyUpdateResponse(BaseModel):
    plugin_name: str
    updated_dependencies: List[str] = Field(default_factory=list)
    applied_updates: Dict[str, str] = Field(default_factory=dict)
    dry_run: bool = False
    conflicts: Dict[str, List[str]] = Field(default_factory=dict)
    missing_dependencies: List[str] = Field(default_factory=list)
    health_checks: List[PluginDependencyHealthItem] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    lock_file_path: Optional[str] = None
    lock_content: Optional[str] = None


class PluginDependencyConflictsResponse(BaseModel):
    plugin_name: str
    conflicts: Dict[str, List[str]] = Field(default_factory=dict)
    missing_dependencies: List[str] = Field(default_factory=list)
    health_checks: List[PluginDependencyHealthItem] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    lock_file_path: Optional[str] = None
    lock_content: Optional[str] = None


class BulkDependencyUpdateOperation(BaseModel):
    plugin_name: str
    updates: Dict[str, str] = Field(default_factory=dict)
    pin_versions: bool = Field(default=False)
    import_lock_content: Optional[str] = Field(default=None)


class BulkDependencyUpdateRequest(BaseModel):
    operations: List[BulkDependencyUpdateOperation] = Field(default_factory=list)
    dry_run: bool = Field(default=False)
    rollback_on_error: bool = Field(default=True)
    allow_conflicts: bool = Field(default=False)
    export_lock: bool = Field(default=True)


class BulkDependencyUpdateResponse(BaseModel):
    updated: List[PluginDependencyUpdateResponse] = Field(default_factory=list)
    errors: List[Dict[str, str]] = Field(default_factory=list)
    rolled_back: bool = Field(default=False)


class HotReloadLogEntry(BaseModel):
    timestamp: str
    event_type: str
    plugin_name: Optional[str] = None
    success: Optional[bool] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class HotReloadStatusResponse(BaseModel):
    enabled: bool
    running: bool
    watchdog_available: bool
    watch_directories: List[str] = Field(default_factory=list)
    debounce_ms: int = 500
    events_total: int = 0
    recent_logs: List[HotReloadLogEntry] = Field(default_factory=list)
    plugin_health: List[Dict[str, Any]] = Field(default_factory=list)
    performance: Dict[str, Any] = Field(default_factory=dict)
    alerts: List[Dict[str, Any]] = Field(default_factory=list)
    alerting: Dict[str, Any] = Field(default_factory=dict)


class HotReloadToggleResponse(BaseModel):
    enabled: bool
    running: bool
    watchdog_available: bool
    message: str


class PluginReloadHistoryResponse(BaseModel):
    plugin_name: str
    history: List[HotReloadLogEntry] = Field(default_factory=list)


class PluginReloadNowResponse(BaseModel):
    plugin_name: str
    reloaded: bool
    message: str
    event: Optional[HotReloadLogEntry] = None


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., min_length=1, max_length=64)
    value: str = Field(..., min_length=1, max_length=4096)
    expires_at: Optional[str] = Field(default=None)


class ApiKeyUpdateRequest(BaseModel):
    value: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    expires_at: Optional[str] = Field(default=None)


class ApiKeyListItem(BaseModel):
    name: str
    type: str
    status: str
    last_used_at: Optional[str] = None
    created_at: Optional[str] = None
    masked_value: Optional[str] = None


class ApiKeyListResponse(BaseModel):
    keys: List[ApiKeyListItem] = Field(default_factory=list)


class ApiKeyValidateResponse(BaseModel):
    valid: bool
    error: Optional[str] = None


class ApiKeyHealthItem(BaseModel):
    name: str
    type: str
    status: str
    last_validation: Optional[str] = None
    expires_in_days: Optional[int] = None


class ApiKeysHealthResponse(BaseModel):
    total_keys: int = 0
    valid_keys: int = 0
    invalid_keys: int = 0
    expiring_soon: int = 0
    rotation_required: bool = False
    keys: List[ApiKeyHealthItem] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str
