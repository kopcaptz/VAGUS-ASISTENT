"""
Pydantic модели конфигурации для Vagus Asistent.
Основано на рекомендациях GPT.
"""

import re
from enum import Enum
from typing import Dict, List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    field_serializer,
    field_validator,
    model_validator,
)


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
    
    @field_validator("workspace_path")
    @classmethod
    def validate_workspace_path(cls, v: str) -> str:
        """Валидация пути к workspace."""
        import os

        if not os.path.isabs(v):
            from pathlib import Path

            project_root = Path(__file__).parent.parent.parent.parent
            v = str(project_root / v)
        return v

    @field_validator("default_model")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        """Валидация имени модели."""
        if not v or len(v.strip()) < 2:
            raise ValueError("Model name must be at least 2 characters")
        return v.strip()


class ProviderConfig(BaseModel):
    """Конфигурация провайдера LLM."""
    api_key: SecretStr = Field(..., description="API ключ (загружается из .env)")
    endpoint: HttpUrl = Field(..., description="URL endpoint API")
    rate_limit: int = Field(default=60, ge=1, le=1000, description="Лимит запросов в минуту")
    timeout: int = Field(default=30, ge=1, le=300, description="Таймаут запроса в секундах")
    enabled: bool = Field(default=True, description="Включен ли провайдер")
    models: List[str] = Field(default_factory=list, description="Доступные модели")
    
    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: HttpUrl) -> HttpUrl:
        """Валидация endpoint URL."""
        url_str = str(v)
        if not url_str.startswith(("http://", "https://")):
            raise ValueError("Endpoint must start with http:// or https://")
        return v

    @field_serializer("api_key")
    def serialize_api_key(self, api_key: SecretStr, _info):
        """Сериализация API ключа (маскирование)."""
        return "**********" if api_key else ""


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
    
    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Валидация температуры."""
        if v < 0.0 or v > 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")
        return round(v, 2)

    @field_validator("model")
    @classmethod
    def validate_model_reference(cls, v: str) -> str:
        """Валидация ссылки на модель."""
        if not v or len(v.strip()) < 2:
            raise ValueError("Model reference must be at least 2 characters")
        return v.strip()


class SkillConfig(BaseModel):
    """Конфигурация навыка."""
    name: str = Field(..., description="Имя навыка")
    description: str = Field(..., description="Описание навыка")
    version: str = Field(default="1.0.0", description="Версия навыка")
    enabled: bool = Field(default=True, description="Включен ли навык")
    dependencies: List[str] = Field(default_factory=list, description="Зависимости навыка")
    category: Optional[str] = Field(None, description="Категория навыка")
    
    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Валидация версии (семантическое версионирование)."""
        pattern = r"^\d+\.\d+\.\d+$"
        if not re.match(pattern, v):
            raise ValueError("Version must follow semantic versioning (e.g., 1.0.0)")
        return v


class AppConfig(BaseModel):
    """Основная конфигурация приложения."""
    version: int = Field(default=1, ge=1, description="Версия конфигурации")
    name: str = Field(default="Vagus Asistent", description="Название приложения")
    global_settings: GlobalConfig = Field(alias="global", description="Глобальные настройки")
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict, description="Провайдеры LLM")
    agents: Dict[str, AgentConfig] = Field(default_factory=dict, description="Агенты")
    skills: Dict[str, SkillConfig] = Field(default_factory=dict, description="Навыки")
    
    @field_validator("version")
    @classmethod
    def validate_version(cls, v: int) -> int:
        """Валидация версии конфигурации."""
        if v < 1:
            raise ValueError("Configuration version must be at least 1")
        return v

    @model_validator(mode="after")
    def validate_agent_skills(self):
        """Валидация навыков агентов."""
        available_skills = set(self.skills.keys())

        for agent_name, agent_config in self.agents.items():
            for skill in agent_config.skills:
                if skill not in available_skills:
                    raise ValueError(f'Agent "{agent_name}" references unknown skill: {skill}')
        return self

    model_config = ConfigDict(populate_by_name=True)