"""
Управление CLI-конфигурацией (~/.vagus/config.json).
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path.home() / ".vagus"
CONFIG_FILE = CONFIG_DIR / "config.json"

_DEFAULTS = {
    "api_url": "http://localhost:8000",
    "api_key": "",
}


def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> Dict[str, Any]:
    """Загружает конфигурацию из файла."""
    if not CONFIG_FILE.exists():
        return dict(_DEFAULTS)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**_DEFAULTS, **data}
    except Exception:
        return dict(_DEFAULTS)


def save_config(data: Dict[str, Any]) -> None:
    """Сохраняет конфигурацию в файл."""
    ensure_config_dir()
    current = load_config()
    current.update(data)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)


def get_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """Возвращает значение из конфигурации."""
    cfg = load_config()
    return cfg.get(key, default)
