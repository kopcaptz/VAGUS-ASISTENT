from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from vagus.security import KeyManager


def test_migration_dry_run_is_default(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=sk-dryrun-123456789\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dryrun-123456789")
    KeyManager.reset_instance_for_tests()

    result = subprocess.run(
        [sys.executable, "scripts/migrate_env_to_encrypted.py", "--env-file", str(env_path)],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ),
    )
    assert result.returncode == 0
    assert "Dry-run mode" in result.stdout
    manager = KeyManager()
    keys_file = tmp_path / ".vagus" / "keys.enc"
    assert not keys_file.exists()


def test_migration_apply_creates_env_backup(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=sk-live-1234567890\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-live-1234567890")
    KeyManager.reset_instance_for_tests()

    result = subprocess.run(
        [
            sys.executable,
            "scripts/migrate_env_to_encrypted.py",
            "--env-file",
            str(env_path),
            "--apply",
            "--force",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ),
    )
    assert result.returncode == 0
    backups = list(tmp_path.glob(".env.backup_*"))
    assert backups, "Expected .env backup file"
    manager = KeyManager()
    assert "openai" in manager.list_keys()
