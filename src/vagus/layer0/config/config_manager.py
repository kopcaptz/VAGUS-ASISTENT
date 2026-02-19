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

_SENTINEL = object()
from pydantic import ValidationError

from .models import AppConfig

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
        """Внедряет секреты из переменных окружения в конфигурацию."""
        if 'providers' not in config_data:
            return config_data
        
        import os
        from pydantic import SecretStr
        
        for provider_name, provider_config in config_data['providers'].items():
            # Получаем API ключ из переменных окружения
            secret_key = f"{provider_name.upper()}_API_KEY"
            api_key = os.getenv(secret_key)
            
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

    def get(self, dotted_path: str, default: Any = None) -> Any:
        """
        Retrieves a config value by dot-separated path.

        Examples:
            cm.get("layer1.cache.ttl_seconds")     -> 3600
            cm.get("global.default_model")          -> "gpt-4"
            cm.get("layer3.api.port", 8000)         -> 8000

        Args:
            dotted_path: Dot-separated path (e.g. "layer1.router.enable_cache")
            default: Value returned when the path does not exist

        Returns:
            The resolved value or *default*.
        """
        config = self.get_config()
        obj: Any = config
        for part in dotted_path.split("."):
            # "global" is an alias stored as "global_settings" on the model
            if part == "global":
                part = "global_settings"
            if isinstance(obj, dict):
                obj = obj.get(part, _SENTINEL)
            elif hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                return default
            if obj is _SENTINEL:
                return default
        return obj

    def set(self, dotted_path: str, value: Any) -> None:
        """
        Sets a config value at runtime (in-memory only, not persisted).

        Args:
            dotted_path: Dot-separated path
            value: New value
        """
        config = self.get_config()
        parts = dotted_path.split(".")
        obj: Any = config
        for part in parts[:-1]:
            if part == "global":
                part = "global_settings"
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                raise KeyError(f"Config path not found: {dotted_path}")
        last = parts[-1]
        if last == "global":
            last = "global_settings"
        if hasattr(obj, last):
            setattr(obj, last, value)
        else:
            raise KeyError(f"Config path not found: {dotted_path}")

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