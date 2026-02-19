"""
Pydantic модели конфигурации для Vagus Asistent.
Основано на рекомендациях GPT.
"""

from pydantic import BaseModel, Field, SecretStr, HttpUrl, validator, field_serializer
from typing import Dict, List, Optional, Any
from enum import Enum
import re


class LogLevel(str, Enum):
    """Уровни логирования."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class GlobalConfig(BaseModel):
    """Глобальные настройки."""
    default_model: str = Field(default="gpt-4", description="Модель по умолчанию")
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Уровень логирования")
    workspace_path: str = Field(default="./workspace", description="Путь к рабочей директории")
    max_concurrent_requests: int = Field(default=10, ge=1, le=100, description="Максимум параллельных запросов")
    api_timeout: int = Field(default=30, ge=1, le=300, description="Таймаут API запросов в секундах")
    
    @validator('workspace_path')
    def validate_workspace_path(cls, v):
        """Валидация пути к workspace."""
        import os
        if not os.path.isabs(v):
            from pathlib import Path
            project_root = Path(__file__).parent.parent.parent.parent
            v = str(project_root / v)
        return v
    
    @validator('default_model')
    def validate_model_name(cls, v):
        """Валидация имени модели."""
        if not v or len(v.strip()) < 2:
            raise ValueError('Model name must be at least 2 characters')
        return v.strip()


class ProviderConfig(BaseModel):
    """Конфигурация провайдера LLM."""
    api_key: SecretStr = Field(..., description="API ключ (загружается из .env)")
    endpoint: HttpUrl = Field(..., description="URL endpoint API")
    rate_limit: int = Field(default=60, ge=1, le=1000, description="Лимит запросов в минуту")
    timeout: int = Field(default=30, ge=1, le=300, description="Таймаут запроса в секундах")
    enabled: bool = Field(default=True, description="Включен ли провайдер")
    models: List[str] = Field(default_factory=list, description="Доступные модели")
    
    @validator('endpoint')
    def validate_endpoint(cls, v):
        """Валидация endpoint URL."""
        url_str = str(v)
        if not url_str.startswith(('http://', 'https://')):
            raise ValueError('Endpoint must start with http:// or https://')
        return v
    
    @field_serializer('api_key')
    def serialize_api_key(self, api_key: SecretStr, _info):
        """Сериализация API ключа (маскирование)."""
        return "**********" if api_key else ""
    
    class Config:
        json_encoders = {
            SecretStr: lambda v: "**********" if v else ""
        }


class AgentConfig(BaseModel):
    """Конфигурация агента."""
    name: str = Field(..., description="Имя агента")
    description: Optional[str] = Field(None, description="Описание агента")
    model: str = Field(..., description="Модель LLM для агента")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Температура генерации")
    max_tokens: int = Field(default=1000, ge=1, le=100000, description="Максимум токенов в ответе")
    top_p: float = Field(default=1.0, ge=0.0, le=1.0, description="Top-p параметр")
    top_k: Optional[int] = Field(None, ge=1, le=100, description="Top-k параметр")
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0, description="Штраф за частоту")
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0, description="Штраф за присутствие")
    skills: List[str] = Field(default_factory=list, description="Список навыков агента")
    enabled: bool = Field(default=True, description="Включен ли агент")
    
    @validator('temperature')
    def validate_temperature(cls, v):
        """Валидация температуры."""
        if v < 0.0 or v > 2.0:
            raise ValueError('Temperature must be between 0.0 and 2.0')
        return round(v, 2)
    
    @validator('model')
    def validate_model_reference(cls, v, values):
        """Валидация ссылки на модель."""
        if not v or len(v.strip()) < 2:
            raise ValueError('Model reference must be at least 2 characters')
        return v.strip()


class SkillConfig(BaseModel):
    """Конфигурация навыка."""
    name: str = Field(..., description="Имя навыка")
    description: str = Field(..., description="Описание навыка")
    version: str = Field(default="1.0.0", description="Версия навыка")
    enabled: bool = Field(default=True, description="Включен ли навык")
    dependencies: List[str] = Field(default_factory=list, description="Зависимости навыка")
    category: Optional[str] = Field(None, description="Категория навыка")
    
    @validator('version')
    def validate_version(cls, v):
        """Валидация версии (семантическое версионирование)."""
        pattern = r'^\d+\.\d+\.\d+$'
        if not re.match(pattern, v):
            raise ValueError('Version must follow semantic versioning (e.g., 1.0.0)')
        return v


class WebSocketConfig(BaseModel):
    """Конфигурация WebSocket hardening."""

    max_message_size_mb: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Максимальный размер входящего сообщения в MB",
    )
    ping_interval_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Интервал отправки ping сервером",
    )
    ping_timeout_seconds: int = Field(
        default=60,
        ge=1,
        le=600,
        description="Таймаут ожидания pong от клиента",
    )
    max_messages_per_minute: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Лимит входящих сообщений в минуту на соединение",
    )


class SecurityRateLimitConfig(BaseModel):
    """Ролевые лимиты API-запросов."""

    anonymous_requests_per_minute: int = Field(default=10, ge=1, le=100000)
    user_requests_per_minute: int = Field(default=100, ge=1, le=100000)
    admin_requests_per_minute: int = Field(default=1000, ge=1, le=100000)
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis URL для rate limiter (если не задан, используется in-memory)",
    )


class SecurityConfig(BaseModel):
    """Конфигурация общих security-настроек API."""

    admin_ip_whitelist: List[str] = Field(
        default_factory=list,
        description="Список IP/CIDR, которым разрешён доступ к /api/v1/admin/*",
    )
    enable_request_signing: bool = Field(
        default=False,
        description="Требовать HMAC-подпись запросов от CLI",
    )
    request_signing_ttl_seconds: int = Field(
        default=300,
        ge=1,
        le=3600,
        description="Допустимая разница времени для подписи запроса",
    )
    request_signing_credentials_path: Optional[str] = Field(
        default=None,
        description="Путь к client_credentials.json для server-side verification",
    )
    audit_db_path: str = Field(
        default="audit_trail.db",
        description="SQLite файл для unified audit trail",
    )
    dead_letter_queue_db_path: str = Field(
        default="dead_letter_queue.db",
        description="SQLite файл для Dead Letter Queue",
    )
    error_analytics_db_path: str = Field(
        default="error_analytics.db",
        description="SQLite файл для error analytics",
    )
    rate_limit: SecurityRateLimitConfig = Field(default_factory=SecurityRateLimitConfig)


class JWTConfig(BaseModel):
    """Конфигурация ротации JWT секретов."""

    secret_rotation_days: int = Field(
        default=30,
        ge=1,
        le=3650,
        description="Период ротации JWT-секрета",
    )
    max_old_secrets: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Сколько старых секретов сохранять для graceful rotation",
    )


class SecretsConfig(BaseModel):
    """Конфигурация secrets backend."""

    backend: str = Field(
        default="local",
        description="Backend для secrets: local или vault",
    )
    vault_addr: Optional[str] = Field(default=None, description="URL Hashicorp Vault")
    vault_token: Optional[str] = Field(default=None, description="Токен Vault")

    @validator("backend")
    def validate_backend(cls, v):
        value = (v or "").strip().lower()
        if value not in {"local", "vault"}:
            raise ValueError("secrets.backend must be 'local' or 'vault'")
        return value


class RetryConfig(BaseModel):
    """Конфигурация retry/backoff."""

    max_attempts: int = Field(default=5, ge=1, le=20)
    backoff_factor: float = Field(default=2.0, ge=1.0, le=10.0)
    retryable_errors: List[str] = Field(
        default_factory=lambda: ["timeout", "rate_limit", "network_error"]
    )


class TaskTimeoutsConfig(BaseModel):
    """Таймауты задач по типу агента."""

    researcher: int = Field(default=300, ge=1, le=3600)
    coder: int = Field(default=600, ge=1, le=3600)
    analyst: int = Field(default=180, ge=1, le=3600)


class PluginsSandboxConfig(BaseModel):
    """Ограничения sandbox-исполнения плагинов."""

    enabled: bool = Field(default=True)
    memory_limit_mb: int = Field(default=512, ge=64, le=16384)
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    filesystem_whitelist: List[str] = Field(
        default_factory=lambda: ["/tmp", "./data"],
        description="Разрешённые пути файловой системы для plugin sandbox",
    )
    network_whitelist: List[str] = Field(
        default_factory=lambda: ["api.openai.com", "api.anthropic.com"],
        description="Разрешённые домены для sandbox network access",
    )

    @validator("filesystem_whitelist", "network_whitelist")
    def validate_whitelists(cls, v):
        normalized = [str(item).strip() for item in v if str(item).strip()]
        return normalized


class PluginsMarketplaceConfig(BaseModel):
    """Настройки marketplace плагинов."""

    url: str = Field(default="https://plugins.vagus.ai")
    cache_ttl_hours: int = Field(default=24, ge=1, le=720)


class PluginsSecurityConfig(BaseModel):
    """Security-настройки плагинной системы."""

    require_signatures: bool = Field(default=False)
    trusted_keys: List[str] = Field(default_factory=list)
    max_plugin_dependencies: int = Field(default=10, ge=0, le=100)
    banned_imports: List[str] = Field(
        default_factory=lambda: ["os.system", "subprocess.Popen", "ctypes"]
    )

    @validator("trusted_keys", "banned_imports")
    def validate_string_list_values(cls, v):
        return [str(item).strip() for item in v if str(item).strip()]


class PluginsConfig(BaseModel):
    """Конфигурация плагинной системы."""

    enabled: bool = Field(default=True)
    auto_discover: bool = Field(default=True)
    scan_directories: List[str] = Field(
        default_factory=lambda: ["./plugins", "~/.vagus/plugins"]
    )
    sandbox: PluginsSandboxConfig = Field(default_factory=PluginsSandboxConfig)
    security: PluginsSecurityConfig = Field(default_factory=PluginsSecurityConfig)
    marketplace: PluginsMarketplaceConfig = Field(default_factory=PluginsMarketplaceConfig)

    @validator("scan_directories")
    def validate_scan_directories(cls, v):
        if not v:
            raise ValueError("plugins.scan_directories must contain at least one directory")
        normalized = [str(item).strip() for item in v if str(item).strip()]
        if not normalized:
            raise ValueError("plugins.scan_directories must contain valid directory paths")
        return normalized


class AppConfig(BaseModel):
    """Основная конфигурация приложения."""
    version: int = Field(default=1, ge=1, description="Версия конфигурации")
    name: str = Field(default="Vagus Asistent", description="Название приложения")
    global_settings: GlobalConfig = Field(alias="global", description="Глобальные настройки")
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict, description="Провайдеры LLM")
    agents: Dict[str, AgentConfig] = Field(default_factory=dict, description="Агенты")
    skills: Dict[str, SkillConfig] = Field(default_factory=dict, description="Навыки")
    websocket: WebSocketConfig = Field(default_factory=WebSocketConfig, description="Настройки WebSocket")
    security: SecurityConfig = Field(default_factory=SecurityConfig, description="Security настройки API")
    jwt: JWTConfig = Field(default_factory=JWTConfig, description="Настройки JWT")
    retry: RetryConfig = Field(default_factory=RetryConfig, description="Retry/backoff настройки")
    task_timeouts: TaskTimeoutsConfig = Field(
        default_factory=TaskTimeoutsConfig,
        description="Таймауты задач по типам агентов",
    )
    plugins: PluginsConfig = Field(default_factory=PluginsConfig, description="Настройки плагинов")
    secrets: SecretsConfig = Field(default_factory=SecretsConfig, description="Настройки secrets backend")
    
    @validator('version')
    def validate_version(cls, v):
        """Валидация версии конфигурации."""
        if v < 1:
            raise ValueError('Configuration version must be at least 1')
        return v
    
    @validator('agents')
    def validate_agent_skills(cls, v, values):
        """Валидация навыков агентов."""
        if 'skills' not in values:
            return v
        
        available_skills = set(values['skills'].keys())
        
        for agent_name, agent_config in v.items():
            for skill in agent_config.skills:
                if skill not in available_skills:
                    raise ValueError(f'Agent "{agent_name}" references unknown skill: {skill}')
        
        return v
    
    class Config:
        allow_population_by_field_name = True
        json_encoders = {
            SecretStr: lambda v: "**********" if v else ""
        }