"""Smoke tests for API Keys health dashboard integration."""

from pathlib import Path


def test_api_keys_page_contains_health_controls():
    page_path = Path("dashboard/pages/10_API_Keys.py")
    assert page_path.exists()
    content = page_path.read_text(encoding="utf-8")
    assert "Keys Health" in content
    assert "get_api_keys_health" in content
    assert "run_api_keys_health_check" in content
    assert "Run Health Check" in content


def test_main_dashboard_contains_api_keys_widget():
    main_path = Path("dashboard/main.py")
    assert main_path.exists()
    content = main_path.read_text(encoding="utf-8")
    assert "API Keys Status" in content
    assert "get_api_keys_health" in content
