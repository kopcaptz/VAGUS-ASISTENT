"""
Функции для работы с конфигурацией CLI.
Чтение/запись ~/.vagus/config.json
"""

import json
from pathlib import Path
from typing import Any, Dict


def get_config_path() -> Path:
    """Возвращает путь к файлу конфигурации ~/.vagus/config.json."""
    return Path.home() / ".vagus" / "config.json"


def load_config() -> Dict[str, Any]:
    """Загружает конфигурацию из ~/.vagus/config.json."""
    path = get_config_path()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(api_url: str, api_key: str) -> None:
    """Сохраняет api_url и api_key в ~/.vagus/config.json."""
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    config = {"api_url": api_url.rstrip("/"), "api_key": api_key}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
