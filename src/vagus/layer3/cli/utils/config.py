"""
CLI configuration management.
Stores API URL and API key in ~/.vagus/config.json.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path.home() / ".vagus"
CONFIG_FILE = CONFIG_DIR / "config.json"


def load_config() -> Dict[str, Any]:
    """Loads CLI config from ~/.vagus/config.json."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(data: Dict[str, Any]) -> None:
    """Saves CLI config to ~/.vagus/config.json (merges with existing)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_config()
    existing.update(data)
    CONFIG_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


def get_api_url() -> str:
    """Returns configured API URL."""
    return load_config().get("api_url", "http://localhost:8000")


def get_api_key() -> Optional[str]:
    """Returns configured API key (JWT token)."""
    return load_config().get("api_key")
