"""Тесты server-side request signing middleware."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from vagus.layer3.api.middleware.request_signing import RequestSigningMiddleware
from vagus.layer3.security.request_signing import (
    HEADER_CLIENT_ID,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
    create_request_signature,
)


def _write_credentials(path: Path, *, client_id: str, client_secret: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"client_id": client_id, "client_secret": client_secret}),
        encoding="utf-8",
    )


def _build_app(*, enabled: bool, credentials_path: str, ttl: int = 300) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        RequestSigningMiddleware,
        enabled=enabled,
        credentials_path=credentials_path,
        timestamp_ttl_seconds=ttl,
        exempt_paths={"/health"},
    )

    @app.post("/signed")
    async def signed():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


def test_request_signing_disabled_allows_unsigned(tmp_path):
    credentials_file = tmp_path / "client_credentials.json"
    _write_credentials(credentials_file, client_id="cid", client_secret="sec")

    app = _build_app(enabled=False, credentials_path=str(credentials_file))
    with TestClient(app) as client:
        resp = client.post("/signed", json={"a": 1})
    assert resp.status_code == 200


def test_request_signing_enabled_rejects_missing_headers(tmp_path):
    credentials_file = tmp_path / "client_credentials.json"
    _write_credentials(credentials_file, client_id="cid", client_secret="sec")

    app = _build_app(enabled=True, credentials_path=str(credentials_file))
    with TestClient(app) as client:
        resp = client.post("/signed", json={"a": 1})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Missing request signature headers"


def test_request_signing_enabled_accepts_valid_signature(tmp_path):
    credentials_file = tmp_path / "client_credentials.json"
    client_id = "client-1"
    client_secret = "super-secret"
    _write_credentials(credentials_file, client_id=client_id, client_secret=client_secret)

    app = _build_app(enabled=True, credentials_path=str(credentials_file))
    body = json.dumps({"hello": "world"}, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))
    signature = create_request_signature(
        secret=client_secret,
        method="POST",
        path="/signed",
        timestamp=ts,
        body=body,
        client_id=client_id,
    )

    headers = {
        "Content-Type": "application/json",
        HEADER_CLIENT_ID: client_id,
        HEADER_TIMESTAMP: ts,
        HEADER_SIGNATURE: signature,
    }
    with TestClient(app) as client:
        resp = client.post("/signed", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_request_signing_enabled_rejects_stale_timestamp(tmp_path):
    credentials_file = tmp_path / "client_credentials.json"
    client_id = "client-1"
    client_secret = "super-secret"
    _write_credentials(credentials_file, client_id=client_id, client_secret=client_secret)

    app = _build_app(enabled=True, credentials_path=str(credentials_file), ttl=10)
    body = b"{}"
    stale_ts = str(int(time.time()) - 3600)
    signature = create_request_signature(
        secret=client_secret,
        method="POST",
        path="/signed",
        timestamp=stale_ts,
        body=body,
        client_id=client_id,
    )
    headers = {
        "Content-Type": "application/json",
        HEADER_CLIENT_ID: client_id,
        HEADER_TIMESTAMP: stale_ts,
        HEADER_SIGNATURE: signature,
    }
    with TestClient(app) as client:
        resp = client.post("/signed", content=body, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid request timestamp"


def test_request_signing_enabled_rejects_unknown_client(tmp_path):
    credentials_file = tmp_path / "client_credentials.json"
    _write_credentials(credentials_file, client_id="known-client", client_secret="known-secret")

    app = _build_app(enabled=True, credentials_path=str(credentials_file))
    body = b"{}"
    ts = str(int(time.time()))
    signature = create_request_signature(
        secret="unknown-secret",
        method="POST",
        path="/signed",
        timestamp=ts,
        body=body,
        client_id="unknown-client",
    )
    headers = {
        "Content-Type": "application/json",
        HEADER_CLIENT_ID: "unknown-client",
        HEADER_TIMESTAMP: ts,
        HEADER_SIGNATURE: signature,
    }
    with TestClient(app) as client:
        resp = client.post("/signed", content=body, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Unknown client credentials"


def test_request_signing_exempt_path_not_checked(tmp_path):
    credentials_file = tmp_path / "client_credentials.json"
    _write_credentials(credentials_file, client_id="cid", client_secret="sec")
    app = _build_app(enabled=True, credentials_path=str(credentials_file))

    with TestClient(app) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
