"""Тесты CLI конфигурации."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from vagus.layer3.cli.utils.config import (
    CONFIG_DIR,
    CONFIG_FILE,
    ensure_config_dir,
    get_value,
    load_config,
    save_config,
)


def test_load_config_defaults():
    with patch("vagus.layer3.cli.utils.config.CONFIG_FILE", Path("/tmp/nonexistent_vagus_config.json")):
        cfg = load_config()
        assert cfg["api_url"] == "http://localhost:8000"
        assert cfg["api_key"] == ""


def test_save_and_load_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_file = Path(tmpdir) / "config.json"
        with patch("vagus.layer3.cli.utils.config.CONFIG_FILE", cfg_file), \
             patch("vagus.layer3.cli.utils.config.CONFIG_DIR", Path(tmpdir)):
            save_config({"api_url": "http://test:9000", "api_key": "mykey"})
            cfg = load_config()
            assert cfg["api_url"] == "http://test:9000"
            assert cfg["api_key"] == "mykey"


def test_save_config_merges():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_file = Path(tmpdir) / "config.json"
        with patch("vagus.layer3.cli.utils.config.CONFIG_FILE", cfg_file), \
             patch("vagus.layer3.cli.utils.config.CONFIG_DIR", Path(tmpdir)):
            save_config({"api_url": "http://first:1000"})
            save_config({"api_key": "new-key"})
            cfg = load_config()
            assert cfg["api_url"] == "http://first:1000"
            assert cfg["api_key"] == "new-key"


def test_get_value():
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_file = Path(tmpdir) / "config.json"
        with patch("vagus.layer3.cli.utils.config.CONFIG_FILE", cfg_file), \
             patch("vagus.layer3.cli.utils.config.CONFIG_DIR", Path(tmpdir)):
            save_config({"api_url": "http://val:5000"})
            assert get_value("api_url") == "http://val:5000"
            assert get_value("nonexistent", "fallback") == "fallback"


def test_ensure_config_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        sub = Path(tmpdir) / "sub" / "dir"
        with patch("vagus.layer3.cli.utils.config.CONFIG_DIR", sub):
            ensure_config_dir()
            assert sub.exists()
