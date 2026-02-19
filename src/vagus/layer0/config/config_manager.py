"""
Менеджер конфигурации для Vagus Asistent.
Дополнено hot-reload на основе рекомендаций GPT.
"""

import yaml
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from dotenv import load_dotenv
from pydantic import ValidationError

from .models import AppConfig
from .secrets_manager import SecretsManager

# Импорты для hot-reload (опционально)
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
    _EventHandlerBase = FileSystemEventHandler
except ImportError:
    WATCHDOG_AVAILABLE = False
    _EventHandlerBase = object


class ConfigReloadHandler(_EventHandlerBase):
    """Обработчик событий файловой системы для hot-reload."""
    
    def __init__(self, callback: Callable, config_path: Path, env_path: Path):
        self.callback = callback
        self.config_path = config_path
        self.env_path = env_path
    
    def on_modified(self, event):
        """Вызывается при изменении файла."""
        if event.src_path.endswith(str(self.config_path)) or event.src_path.endswith(str(self.env_path)):
            print("Конфигурационный файл изменён, запуск перезагрузки...")
            try:
                self.callback()
            except Exception as e:
                print(f"Ошибка при перезагрузке конфигурации: {e}")


class ConfigManager:
    """Менеджер конфигурации с поддержкой hot-reload."""
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        env_path: Optional[str] = None,
        enable_hot_reload: bool = True
    ):
        """
        Инициализация менеджера конфигурации.
        
        Args:
            config_path: Путь к YAML файлу конфигурации
            env_path: Путь к .env файлу
            enable_hot_reload: Включить hot-reload
        """
        self.config_path = Path(config_path) if config_path else Path("configs/vagus.yaml")
        self.env_path = Path(env_path) if env_path else Path(".env")
        self.enable_hot_reload = enable_hot_reload and WATCHDOG_AVAILABLE
        
        self._config: Optional[AppConfig] = None
        self._last_modified = 0
        self._observers = []
        self._callbacks = []
        
        # Загружаем переменные окружения
        self._load_env()
        
        # Запускаем hot-reload если включен и доступен
        if self.enable_hot_reload:
            self._start_hot_reload()
    
    def _load_env(self) -> None:
        """Загружает переменные окружения из .env файла."""
        if self.env_path.exists():
            load_dotenv(self.env_path)
            print(f"[OK] Загружены переменные окружения из {self.env_path}")
        else:
            print(f"[WARN] Файл .env не найден: {self.env_path}")
    
    def _load_yaml(self) -> Dict[str, Any]:
        """Загружает YAML конфигурацию."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Конфигурационный файл не найден: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        return data or {}
    
    def _inject_secrets(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Внедряет секреты в конфигурацию через SecretsManager."""
        if 'providers' not in config_data:
            return config_data

        secrets_cfg = config_data.get("secrets", {}) if isinstance(config_data, dict) else {}
        secrets_manager = SecretsManager.from_config(secrets_cfg if isinstance(secrets_cfg, dict) else {})

        for provider_name, provider_config in config_data['providers'].items():
            api_key = secrets_manager.get_provider_api_key(provider_name)

            if api_key:
                provider_config['api_key'] = api_key
            elif 'api_key' not in provider_config:
                print(f"[WARN] API ключ для провайдера {provider_name} не найден")

        return config_data
    
    def _validate_config_data(self, config_data: Dict[str, Any]) -> None:
        """Выполняет дополнительную валидацию данных конфигурации."""
        if 'version' not in config_data:
            raise ValueError("Конфигурация должна содержать поле 'version'")
        
        if 'global' not in config_data:
            raise ValueError("Конфигурация должна содержать секцию 'global'")
    
    def load(self, force_reload: bool = False) -> AppConfig:
        """
        Загружает конфигурацию.
        
        Args:
            force_reload: Принудительная перезагрузка
            
        Returns:
            Загруженная конфигурация
        """
        # Проверяем, изменился ли файл конфигурации
        current_modified = self.config_path.stat().st_mtime if self.config_path.exists() else 0
        
        if not force_reload and self._config and current_modified <= self._last_modified:
            return self._config
        
        try:
            # Загружаем YAML
            yaml_data = self._load_yaml()
            
            # Валидируем структуру
            self._validate_config_data(yaml_data)
            
            # Внедряем секреты
            config_data = self._inject_secrets(yaml_data)
            
            # Создаём Pydantic модель
            self._config = AppConfig(**config_data)
            self._last_modified = current_modified
            
            print(f"[OK] Конфигурация загружена из {self.config_path} (версия: {self._config.version})")
            
            # Вызываем колбэки
            self._notify_callbacks()
            
            return self._config
            
        except ValidationError as e:
            print(f"[ERROR] Ошибка валидации конфигурации: {e}")
            raise
        except Exception as e:
            print(f"[ERROR] Ошибка загрузки конфигурации: {e}")
            raise
    
    def _start_hot_reload(self) -> None:
        """Запускает hot-reload наблюдатель."""
        if not WATCHDOG_AVAILABLE:
            print("[WARN] Watchdog не установлен, hot-reload отключен")
            return
        
        try:
            observer = Observer()
            handler = ConfigReloadHandler(self._hot_reload_callback, self.config_path, self.env_path)
            
            # Наблюдаем за директориями файлов
            observer.schedule(handler, str(self.config_path.parent), recursive=False)
            if self.env_path.parent != self.config_path.parent:
                observer.schedule(handler, str(self.env_path.parent), recursive=False)
            
            observer.start()
            self._observers.append(observer)
            
            print("[OK] Hot-reload наблюдатель запущен")
            
        except Exception as e:
            print(f"[WARN] Не удалось запустить hot-reload: {e}")
    
    def _hot_reload_callback(self) -> None:
        """Колбэк для hot-reload."""
        try:
            self.load(force_reload=True)
        except Exception as e:
            print(f"[ERROR] Ошибка при hot-reload: {e}")
    
    def _notify_callbacks(self) -> None:
        """Уведомляет зарегистрированные колбэки об изменении конфигурации."""
        for callback in self._callbacks:
            try:
                callback(self._config)
            except Exception as e:
                print(f"[ERROR] Ошибка в колбэке конфигурации: {e}")
    
    def register_callback(self, callback: Callable[[AppConfig], None]) -> None:
        """
        Регистрирует колбэк для уведомлений об изменении конфигурации.
        
        Args:
            callback: Функция, принимающая AppConfig
        """
        self._callbacks.append(callback)
        print(f"[OK] Зарегистрирован колбэк конфигурации: {callback.__name__}")
    
    def get_config(self) -> AppConfig:
        """Возвращает текущую конфигурацию (загружает если нужно)."""
        if not self._config:
            return self.load()
        return self._config
    
    def save_default_config(self) -> None:
        """Сохраняет пример конфигурации."""
        default_config = {
            "version": 1,
            "name": "Vagus Asistent",
            "global": {
                "default_model": "gpt-4",
                "log_level": "INFO",
                "workspace_path": "./workspace",
                "max_concurrent_requests": 10,
                "api_timeout": 30
            },
            "websocket": {
                "max_message_size_mb": 10,
                "ping_interval_seconds": 30,
                "ping_timeout_seconds": 60
            },
            "security": {
                "admin_ip_whitelist": ["127.0.0.1", "192.168.1.0/24"],
                "enable_request_signing": False,
                "request_signing_ttl_seconds": 300,
                "request_signing_credentials_path": "~/.vagus/client_credentials.json",
                "audit_db_path": "audit_trail.db",
                "dead_letter_queue_db_path": "dead_letter_queue.db",
                "error_analytics_db_path": "error_analytics.db",
                "rate_limit": {
                    "anonymous_requests_per_minute": 10,
                    "user_requests_per_minute": 100,
                    "admin_requests_per_minute": 1000,
                    "redis_url": None
                }
            },
            "jwt": {
                "secret_rotation_days": 30,
                "max_old_secrets": 3
            },
            "retry": {
                "max_attempts": 5,
                "backoff_factor": 2.0,
                "retryable_errors": ["timeout", "rate_limit", "network_error"],
            },
            "task_timeouts": {
                "researcher": 300,
                "coder": 600,
                "analyst": 180,
            },
            "layer2": {
                "cluster": {
                    "enabled": False,
                    "node_id": "node-local",
                    "stateless_agents": True,
                    "shared_task_queue": {
                        "enabled": False,
                        "redis_url": "redis://localhost:6379/0",
                        "queue_name": "vagus:cluster:tasks",
                    },
                    "distributed_locking": {
                        "enabled": False,
                        "redis_url": "redis://localhost:6379/0",
                        "lock_ttl_seconds": 900,
                    },
                }
            },
            "secrets": {
                "backend": "local",
                "vault_addr": "http://localhost:8200",
                "vault_token": ""
            },
            "providers": {
                "openai": {
                    "endpoint": "https://api.openai.com/v1",
                    "rate_limit": 60,
                    "timeout": 30,
                    "enabled": True,
                    "models": ["gpt-4", "gpt-3.5-turbo"]
                },
                "anthropic": {
                    "endpoint": "https://api.anthropic.com/v1",
                    "rate_limit": 60,
                    "timeout": 30,
                    "enabled": True,
                    "models": ["claude-3-opus", "claude-3-sonnet"]
                }
            },
            "layer1": {
                "http": {
                    "max_connections": 100,
                    "max_keepalive_connections": 20,
                    "keepalive_expiry": 5.0,
                },
                "cache": {
                    "ttl_seconds": 3600,
                    "max_size_mb": 100,
                    "secondary": {
                        "enabled": True,
                        "redis_url": "redis://localhost:6379/0",
                        "sqlite_fallback_path": "cache_fallback.db",
                        "llm_responses_ttl_seconds": 3600,
                        "provider_health_ttl_seconds": 120,
                        "rate_limit_counter_ttl_seconds": 60,
                        "session_data_ttl_seconds": 3600,
                    },
                },
            },
            "monitoring": {
                "memory_profiler": {
                    "enabled": True,
                    "interval_seconds": 30,
                    "history_limit": 1024,
                    "leak_threshold_mb": 100.0,
                    "leak_window_seconds": 300,
                },
                "health": {
                    "thresholds": {
                        "disk_free_percent_min": 10.0,
                        "memory_usage_percent_max": 90.0,
                        "check_timeout_seconds": 2.0,
                        "disk_path": ".",
                    },
                },
            },
            "agents": {
                "coordinator": {
                    "name": "Главный агент",
                    "description": "Координатор задач",
                    "model": "gpt-4",
                    "temperature": 0.7,
                    "max_tokens": 1500,
                    "top_p": 1.0,
                    "skills": ["research", "code", "summary"],
                    "enabled": True
                }
            },
            "skills": {
                "weather": {
                    "name": "Погода",
                    "description": "Получение информации о погоде",
                    "version": "1.0.0",
                    "enabled": True,
                    "dependencies": []
                }
            }
        }
        
        # Создаём директорию если нужно
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
        
        print(f"[OK] Пример конфигурации сохранён в {self.config_path}")