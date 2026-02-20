from __future__ import annotations

from pathlib import Path

from vagus.security import KeyManager
from vagus.security.key_backup import BACKUP_MAGIC, create_backup_file, validate_backup_file


def test_backup_magic_and_validation_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    KeyManager.reset_instance_for_tests()
    manager = KeyManager()
    manager.add_key(name="openai", key_type="openai", value="sk-backup-1234567890")

    backup_path = tmp_path / "backup.vkb"
    create_backup_file(key_manager=manager, backup_path=backup_path)
    raw = backup_path.read_bytes()
    assert raw.startswith(BACKUP_MAGIC + b"\n")

    result = validate_backup_file(key_manager=manager, backup_path=backup_path)
    assert result["valid"] is True
    assert result["checksum_ok"] is True


def test_backup_password_layer_requires_password(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    KeyManager.reset_instance_for_tests()
    manager = KeyManager()
    manager.add_key(name="anthropic", key_type="anthropic", value="sk-ant-1234567890")

    backup_path = tmp_path / "backup_protected.vkb"
    create_backup_file(key_manager=manager, backup_path=backup_path, password="secret123")

    failed = False
    try:
        validate_backup_file(key_manager=manager, backup_path=backup_path)
    except ValueError:
        failed = True
    assert failed is True

    result = validate_backup_file(
        key_manager=manager,
        backup_path=backup_path,
        password="secret123",
    )
    assert result["valid"] is True
