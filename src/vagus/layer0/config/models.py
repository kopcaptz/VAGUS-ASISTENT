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


# ─── Layer-specific configuration models ───────────────────────────


class Layer1RouterConfig(BaseModel):
    """Layer 1 router settings."""
    enable_cache: bool = Field(default=True)
    enable_budgeting: bool = Field(default=True)
    enable_monitoring: bool = Field(default=True)
    default_strategy: str = Field(default="hybrid")


class Layer1CacheConfig(BaseModel):
    """Layer 1 cache settings."""
    ttl_seconds: int = Field(default=3600, ge=1)
    max_size_mb: int = Field(default=100, ge=1)


class Layer1BudgetingConfig(BaseModel):
    """Layer 1 budgeting settings."""
    daily_limit_usd: float = Field(default=10.0, ge=0)
    monthly_limit_usd: float = Field(default=100.0, ge=0)


class Layer1MonitoringConfig(BaseModel):
    """Layer 1 monitoring settings."""
    db_path: str = Field(default="./data/metrics.db")
    retention_days: int = Field(default=30, ge=1)


class Layer1FallbackConfig(BaseModel):
    """Layer 1 fallback / circuit-breaker settings."""
    retry_count: int = Field(default=3, ge=0)
    backoff_factor: float = Field(default=2.0, ge=1.0)
    base_delay_seconds: float = Field(default=1.0, ge=0)
    circuit_breaker_threshold: int = Field(default=5, ge=1)
    providers: List[str] = Field(default_factory=lambda: ["openai", "anthropic", "deepseek"])
    max_retries: Optional[int] = Field(default=None, description="Alias for retry_count")


class Layer1Config(BaseModel):
    """Complete Layer 1 configuration."""
    router: Layer1RouterConfig = Field(default_factory=Layer1RouterConfig)
    cache: Layer1CacheConfig = Field(default_factory=Layer1CacheConfig)
    budgeting: Layer1BudgetingConfig = Field(default_factory=Layer1BudgetingConfig)
    monitoring: Layer1MonitoringConfig = Field(default_factory=Layer1MonitoringConfig)
    fallback: Layer1FallbackConfig = Field(default_factory=Layer1FallbackConfig)


class Layer2OrchestratorConfig(BaseModel):
    """Layer 2 orchestrator settings."""
    max_concurrency: int = Field(default=5, ge=1)
    task_timeout: int = Field(default=300, ge=1)


class Layer2MemoryConfig(BaseModel):
    """Layer 2 memory settings."""
    episodic_enabled: bool = Field(default=True)
    semantic_enabled: bool = Field(default=True)
    max_history: int = Field(default=1000, ge=1)


class Layer2Config(BaseModel):
    """Complete Layer 2 configuration."""
    orchestrator: Layer2OrchestratorConfig = Field(default_factory=Layer2OrchestratorConfig)
    memory: Layer2MemoryConfig = Field(default_factory=Layer2MemoryConfig)


class Layer3ApiConfig(BaseModel):
    """Layer 3 API server settings."""
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:8501"])
    rate_limit_requests: int = Field(default=60, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)


class Layer3AuthConfig(BaseModel):
    """Layer 3 auth settings."""
    access_token_expire_minutes: int = Field(default=15, ge=1)
    refresh_token_expire_days: int = Field(default=7, ge=1)


class Layer3Config(BaseModel):
    """Complete Layer 3 configuration."""
    api: Layer3ApiConfig = Field(default_factory=Layer3ApiConfig)
    auth: Layer3AuthConfig = Field(default_factory=Layer3AuthConfig)


class AppConfig(BaseModel):
    """Основная конфигурация приложения."""
    version: int = Field(default=1, ge=1, description="Версия конфигурации")
    name: str = Field(default="Vagus Asistent", description="Название приложения")
    global_settings: GlobalConfig = Field(alias="global", description="Глобальные настройки")
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict, description="Провайдеры LLM")
    agents: Dict[str, AgentConfig] = Field(default_factory=dict, description="Агенты")
    skills: Dict[str, SkillConfig] = Field(default_factory=dict, description="Навыки")
    layer1: Layer1Config = Field(default_factory=Layer1Config, description="Layer 1 settings")
    layer2: Layer2Config = Field(default_factory=Layer2Config, description="Layer 2 settings")
    layer3: Layer3Config = Field(default_factory=Layer3Config, description="Layer 3 settings")
    
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