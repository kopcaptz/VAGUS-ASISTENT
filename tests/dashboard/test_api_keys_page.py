"""Smoke tests for API Keys dashboard page."""

from pathlib import Path


def test_api_keys_page_exists_and_has_expected_controls():
    page_path = Path("dashboard/pages/10_API_Keys.py")
    assert page_path.exists()
    content = page_path.read_text(encoding="utf-8")
    assert "st.title(\"API Keys\")" in content
    assert "list_api_keys" in content
    assert "create_api_key" in content
    assert "validate_api_key" in content
    assert "delete_api_key" in content
