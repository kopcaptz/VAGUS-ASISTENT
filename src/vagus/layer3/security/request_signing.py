"""
Shared HMAC request-signing primitives for CLI and API middleware.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

HEADER_CLIENT_ID = "X-Vagus-Client-Id"
HEADER_SIGNATURE = "X-Vagus-Signature"
HEADER_TIMESTAMP = "X-Vagus-Timestamp"


def get_default_credentials_path() -> Path:
    raw = os.getenv("VAGUS_CLIENT_CREDENTIALS_PATH", "~/.vagus/client_credentials.json")
    return Path(raw).expanduser()


def _read_credentials_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


def _write_credentials_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def load_or_create_client_credentials(path: Optional[Path] = None) -> dict[str, str]:
    credentials_path = path or get_default_credentials_path()
    existing = _read_credentials_file(credentials_path)
    existing_id = existing.get("client_id")
    existing_secret = existing.get("client_secret")
    if existing_id and existing_secret:
        return {"client_id": str(existing_id), "client_secret": str(existing_secret)}

    credentials = {
        "client_id": str(uuid.uuid4()),
        "client_secret": secrets.token_urlsafe(48),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_credentials_file(credentials_path, credentials)
    return {"client_id": credentials["client_id"], "client_secret": credentials["client_secret"]}


def load_client_secret(client_id: str, path: Optional[Path] = None) -> Optional[str]:
    credentials_path = path or get_default_credentials_path()
    data = _read_credentials_file(credentials_path)
    if not data:
        return None

    # Формат одного клиента.
    if data.get("client_id") == client_id:
        secret = data.get("client_secret")
        return str(secret) if secret else None

    # Формат списка клиентов.
    clients = data.get("clients")
    if isinstance(clients, list):
        for item in clients:
            if isinstance(item, dict) and item.get("client_id") == client_id:
                secret = item.get("client_secret")
                if secret:
                    return str(secret)
    return None


def _body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def build_signature_payload(
    *,
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
    client_id: str,
) -> str:
    return "\n".join(
        [
            method.upper(),
            path,
            timestamp,
            _body_hash(body),
            client_id,
        ]
    )


def create_request_signature(
    *,
    secret: str,
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
    client_id: str,
) -> str:
    payload = build_signature_payload(
        method=method,
        path=path,
        timestamp=timestamp,
        body=body,
        client_id=client_id,
    )
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def verify_request_signature(
    *,
    signature: str,
    secret: str,
    method: str,
    path: str,
    timestamp: str,
    body: bytes,
    client_id: str,
) -> bool:
    expected = create_request_signature(
        secret=secret,
        method=method,
        path=path,
        timestamp=timestamp,
        body=body,
        client_id=client_id,
    )
    return hmac.compare_digest(signature, expected)


def is_timestamp_fresh(timestamp: str, max_age_seconds: int, now_ts: Optional[int] = None) -> bool:
    try:
        value = int(timestamp)
    except (TypeError, ValueError):
        return False
    now = int(now_ts if now_ts is not None else time.time())
    return abs(now - value) <= max_age_seconds
