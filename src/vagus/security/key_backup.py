"""Backup/restore helpers for encrypted API key storage."""

from __future__ import annotations

import base64
import json
import secrets
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

BACKUP_MAGIC = b"VAGUS_KEY_BACKUP_v1"
BACKUP_VERSION = 1
BACKUP_AAD = b"vagus.key.backup.v1"
PASSWORD_AAD = b"vagus.key.backup.password.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _b64e(value: bytes) -> str:
    return base64.b64encode(value).decode("utf-8")


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("utf-8"))


def _derive_key(seed: bytes, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390_000,
    )
    return kdf.derive(seed)


def _split_backup_bytes(raw: bytes) -> tuple[dict[str, Any], bytes]:
    if not raw.startswith(BACKUP_MAGIC + b"\n"):
        raise ValueError("Invalid backup magic bytes")
    idx = raw.find(b"\n", len(BACKUP_MAGIC) + 1)
    if idx < 0:
        raise ValueError("Corrupted backup metadata header")
    meta_line = raw[len(BACKUP_MAGIC) + 1 : idx]
    payload = raw[idx + 1 :]
    meta = json.loads(meta_line.decode("utf-8"))
    if not isinstance(meta, dict):
        raise ValueError("Invalid backup metadata")
    if int(meta.get("version", 0)) != BACKUP_VERSION:
        raise ValueError(f"Unsupported backup version: {meta.get('version')}")
    return meta, payload


def _decrypt_payload(master_key: bytes, meta: dict[str, Any], payload: bytes, password: Optional[str]) -> dict[str, Any]:
    salt = _b64d(str(meta.get("salt", "")))
    nonce = _b64d(str(meta.get("nonce", "")))
    key = _derive_key(master_key, salt)
    outer_plain = AESGCM(key).decrypt(nonce, payload, BACKUP_AAD)

    if bool(meta.get("has_password_layer", False)):
        if not password:
            raise ValueError("Backup requires password for decryption")
        inner = json.loads(outer_plain.decode("utf-8"))
        password_salt = _b64d(str(inner.get("password_salt", "")))
        password_nonce = _b64d(str(inner.get("password_nonce", "")))
        password_cipher = _b64d(str(inner.get("password_ciphertext", "")))
        password_key = _derive_key(password.encode("utf-8"), password_salt)
        plain = AESGCM(password_key).decrypt(password_nonce, password_cipher, PASSWORD_AAD)
    else:
        plain = outer_plain

    payload_data = json.loads(plain.decode("utf-8"))
    if not isinstance(payload_data, dict):
        raise ValueError("Invalid decrypted payload")
    return payload_data


def create_backup_file(
    *,
    key_manager: Any,
    backup_path: Path,
    password: Optional[str] = None,
) -> Path:
    store = key_manager._load_store()  # noqa: SLF001 - internal by design
    keys = store.get("keys", {}) if isinstance(store, dict) else {}
    if not isinstance(keys, dict):
        keys = {}
    plain_payload = json.dumps(store, ensure_ascii=False).encode("utf-8")
    checksum = sha256(plain_payload).hexdigest()

    payload_to_encrypt = plain_payload
    has_password_layer = bool(password)
    if has_password_layer:
        password_salt = secrets.token_bytes(16)
        password_nonce = secrets.token_bytes(12)
        password_key = _derive_key(password.encode("utf-8"), password_salt)
        password_ciphertext = AESGCM(password_key).encrypt(password_nonce, plain_payload, PASSWORD_AAD)
        payload_to_encrypt = json.dumps(
            {
                "password_salt": _b64e(password_salt),
                "password_nonce": _b64e(password_nonce),
                "password_ciphertext": _b64e(password_ciphertext),
            },
            ensure_ascii=False,
        ).encode("utf-8")

    master_key = key_manager._get_master_key()  # noqa: SLF001 - internal by design
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    key = _derive_key(master_key, salt)
    encrypted_payload = AESGCM(key).encrypt(nonce, payload_to_encrypt, BACKUP_AAD)

    metadata = {
        "version": BACKUP_VERSION,
        "timestamp": _utc_now(),
        "key_count": len(keys),
        "checksum": checksum,
        "has_password_layer": has_password_layer,
        "salt": _b64e(salt),
        "nonce": _b64e(nonce),
    }
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    output = BACKUP_MAGIC + b"\n" + json.dumps(metadata, ensure_ascii=False).encode("utf-8") + b"\n" + encrypted_payload
    backup_path.write_bytes(output)
    return backup_path


def validate_backup_file(
    *,
    key_manager: Any,
    backup_path: Path,
    password: Optional[str] = None,
) -> dict[str, Any]:
    raw = backup_path.read_bytes()
    metadata, encrypted_payload = _split_backup_bytes(raw)
    decrypted = _decrypt_payload(
        key_manager._get_master_key(),  # noqa: SLF001 - internal by design
        metadata,
        encrypted_payload,
        password,
    )
    plain = json.dumps(decrypted, ensure_ascii=False).encode("utf-8")
    checksum_ok = sha256(plain).hexdigest() == str(metadata.get("checksum", ""))
    return {
        "valid": bool(checksum_ok),
        "metadata": metadata,
        "key_count_actual": len(decrypted.get("keys", {})) if isinstance(decrypted.get("keys"), dict) else 0,
        "decryption_ok": True,
        "checksum_ok": checksum_ok,
    }


def restore_backup_file(
    *,
    key_manager: Any,
    backup_path: Path,
    strategy: str = "merge",
    password: Optional[str] = None,
) -> dict[str, Any]:
    raw = backup_path.read_bytes()
    metadata, encrypted_payload = _split_backup_bytes(raw)
    payload = _decrypt_payload(
        key_manager._get_master_key(),  # noqa: SLF001 - internal by design
        metadata,
        encrypted_payload,
        password,
    )
    if not isinstance(payload, dict):
        raise ValueError("Restored payload is invalid")
    keys = payload.get("keys", {})
    if not isinstance(keys, dict):
        raise ValueError("Restored payload has invalid keys data")

    current = key_manager._load_store()  # noqa: SLF001 - internal by design
    if not isinstance(current, dict):
        current = {"version": 1, "keys": {}}
    current_keys = current.setdefault("keys", {})
    if not isinstance(current_keys, dict):
        current_keys = {}
        current["keys"] = current_keys

    mode = (strategy or "merge").strip().lower()
    if mode == "replace":
        current["keys"] = keys
    elif mode == "merge":
        for name, entry in keys.items():
            current_keys[name] = entry
    else:
        raise ValueError("strategy must be 'merge' or 'replace'")

    key_manager._save_store(current)  # noqa: SLF001 - internal by design
    return {
        "restored_count": len(keys),
        "strategy": mode,
        "metadata": metadata,
    }
