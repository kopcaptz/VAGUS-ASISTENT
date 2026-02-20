from __future__ import annotations

from pathlib import Path


def test_setup_windows_batch_script_exists_and_has_silent_mode() -> None:
    script = Path("scripts/setup_windows_keys.bat")
    assert script.exists()
    content = script.read_text(encoding="utf-8").lower()
    assert "--silent" in content
    assert "python 3.10+" in content


def test_setup_windows_powershell_script_exists_and_has_silent_mode() -> None:
    script = Path("scripts/setup_windows_keys.ps1")
    assert script.exists()
    content = script.read_text(encoding="utf-8").lower()
    assert "$silent" in content
    assert "python 3.10+" in content
