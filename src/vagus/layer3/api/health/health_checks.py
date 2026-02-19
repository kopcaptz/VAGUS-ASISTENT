"""
Detailed health checks for dependencies and infrastructure.
"""

from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error, parse, request

from fastapi import APIRouter, Request

from vagus.layer0.config.secrets_manager import SecretsManager


@dataclass
class HealthThresholds:
    disk_free_percent_min: float = 10.0
    memory_usage_percent_max: float = 90.0
    check_timeout_seconds: float = 2.0
    disk_path: str = "."


def load_health_thresholds(config_data: Optional[dict[str, Any]]) -> HealthThresholds:
    data = config_data or {}
    monitoring_cfg = data.get("monitoring", {}) if isinstance(data, dict) else {}
    health_cfg = monitoring_cfg.get("health", {}) if isinstance(monitoring_cfg, dict) else {}
    thresholds_cfg = health_cfg.get("thresholds", {}) if isinstance(health_cfg, dict) else {}
    if not isinstance(thresholds_cfg, dict):
        thresholds_cfg = {}

    def _to_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    disk_path = thresholds_cfg.get("disk_path", ".")
    if not isinstance(disk_path, str) or not disk_path.strip():
        disk_path = "."

    return HealthThresholds(
        disk_free_percent_min=_to_float(
            thresholds_cfg.get("disk_free_percent_min"),
            10.0,
        ),
        memory_usage_percent_max=_to_float(
            thresholds_cfg.get("memory_usage_percent_max"),
            90.0,
        ),
        check_timeout_seconds=_to_float(
            thresholds_cfg.get("check_timeout_seconds"),
            2.0,
        ),
        disk_path=disk_path,
    )


def _new_check_result(
    *,
    status: str,
    details: Optional[dict[str, Any]] = None,
    error_message: Optional[str] = None,
    latency_ms: Optional[float] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": status, "details": details or {}}
    if error_message:
        payload["error"] = error_message
    if latency_ms is not None:
        payload["latency_ms"] = round(latency_ms, 2)
    return payload


def _check_sqlite_connectivity(db_path: str, timeout_seconds: float) -> dict[str, Any]:
    started_at = time.monotonic()
    try:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path, timeout=timeout_seconds)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        finally:
            conn.close()
        return _new_check_result(
            status="ok",
            details={"db_path": db_path},
            latency_ms=(time.monotonic() - started_at) * 1000,
        )
    except Exception as exc:
        return _new_check_result(
            status="failed",
            details={"db_path": db_path},
            error_message=str(exc),
            latency_ms=(time.monotonic() - started_at) * 1000,
        )


def _check_redis_connectivity(redis_url: Optional[str], timeout_seconds: float) -> dict[str, Any]:
    if not redis_url:
        return _new_check_result(status="skipped", details={"reason": "redis_url_not_configured"})

    started_at = time.monotonic()
    parsed = parse.urlparse(redis_url)
    host = parsed.hostname
    port = parsed.port or 6379
    if not host:
        return _new_check_result(
            status="failed",
            details={"redis_url": redis_url},
            error_message="Invalid redis URL",
        )
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            pass
        return _new_check_result(
            status="ok",
            details={"host": host, "port": port},
            latency_ms=(time.monotonic() - started_at) * 1000,
        )
    except Exception as exc:
        return _new_check_result(
            status="failed",
            details={"host": host, "port": port},
            error_message=str(exc),
            latency_ms=(time.monotonic() - started_at) * 1000,
        )


def _check_llm_providers(llm_router: Any) -> dict[str, Any]:
    providers = getattr(llm_router, "_providers", {}) if llm_router is not None else {}
    if not isinstance(providers, dict) or not providers:
        return _new_check_result(
            status="degraded",
            details={"reason": "no_providers_registered", "providers": {}},
        )

    provider_details: dict[str, Any] = {}
    healthy_count = 0
    for provider_id, provider in providers.items():
        available = False
        model = None
        try:
            available = bool(provider.is_available())
            model = getattr(provider, "model", None)
        except Exception:
            available = False
        provider_details[str(provider_id)] = {
            "available": available,
            "model": model,
        }
        if available:
            healthy_count += 1

    if healthy_count == len(provider_details):
        status = "ok"
    elif healthy_count == 0:
        status = "failed"
    else:
        status = "degraded"

    return _new_check_result(
        status=status,
        details={
            "healthy_providers": healthy_count,
            "total_providers": len(provider_details),
            "providers": provider_details,
        },
    )


def _check_secrets_manager_connectivity(
    secrets_cfg: Optional[dict[str, Any]],
    timeout_seconds: float,
) -> dict[str, Any]:
    cfg = secrets_cfg if isinstance(secrets_cfg, dict) else {}
    backend = str(cfg.get("backend", "local")).strip().lower() or "local"
    started_at = time.monotonic()

    if backend == "vault":
        vault_addr = cfg.get("vault_addr")
        vault_token = cfg.get("vault_token")
        if not vault_addr or not vault_token:
            return _new_check_result(
                status="failed",
                details={"backend": "vault"},
                error_message="vault_addr or vault_token is missing",
            )
        health_url = str(vault_addr).rstrip("/") + "/v1/sys/health"
        req = request.Request(health_url, method="GET", headers={"X-Vault-Token": str(vault_token)})
        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                code = getattr(response, "status", 200)
            status = "ok" if int(code) < 500 else "failed"
            return _new_check_result(
                status=status,
                details={"backend": "vault", "http_status": int(code)},
                latency_ms=(time.monotonic() - started_at) * 1000,
            )
        except error.HTTPError as exc:
            code = int(getattr(exc, "code", 0))
            # Vault can return non-200 statuses for standby/sealed states, but connectivity is still present.
            status = "ok" if 200 <= code < 500 else "failed"
            return _new_check_result(
                status=status,
                details={"backend": "vault", "http_status": code},
                error_message=str(exc) if status == "failed" else None,
                latency_ms=(time.monotonic() - started_at) * 1000,
            )
        except Exception as exc:
            return _new_check_result(
                status="failed",
                details={"backend": "vault"},
                error_message=str(exc),
                latency_ms=(time.monotonic() - started_at) * 1000,
            )

    # local backend: validate that facade can be created and accessed
    try:
        manager = SecretsManager.from_config(cfg)
        manager.get_secret("VAGUS_HEALTHCHECK_DUMMY")
        return _new_check_result(
            status="ok",
            details={"backend": backend},
            latency_ms=(time.monotonic() - started_at) * 1000,
        )
    except Exception as exc:
        return _new_check_result(
            status="failed",
            details={"backend": backend},
            error_message=str(exc),
            latency_ms=(time.monotonic() - started_at) * 1000,
        )


def _check_disk_space(thresholds: HealthThresholds) -> dict[str, Any]:
    target_path = thresholds.disk_path or "."
    usage = shutil.disk_usage(target_path)
    free_percent = (usage.free / usage.total * 100.0) if usage.total > 0 else 0.0
    status = "ok" if free_percent >= thresholds.disk_free_percent_min else "failed"
    return _new_check_result(
        status=status,
        details={
            "path": target_path,
            "free_percent": round(free_percent, 2),
            "threshold_min_free_percent": thresholds.disk_free_percent_min,
            "free_bytes": int(usage.free),
            "total_bytes": int(usage.total),
        },
    )


def _read_memory_usage_percent() -> Optional[float]:
    meminfo_path = "/proc/meminfo"
    if not os.path.exists(meminfo_path):
        return None

    total_kb = None
    available_kb = None
    with open(meminfo_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                available_kb = int(line.split()[1])
            if total_kb is not None and available_kb is not None:
                break

    if not total_kb or available_kb is None:
        return None
    used_percent = 100.0 * (1.0 - (available_kb / total_kb))
    return max(0.0, min(100.0, used_percent))


def _check_memory_usage(thresholds: HealthThresholds) -> dict[str, Any]:
    used_percent = _read_memory_usage_percent()
    if used_percent is None:
        return _new_check_result(status="degraded", details={"reason": "memory_metrics_unavailable"})

    status = "ok" if used_percent <= thresholds.memory_usage_percent_max else "failed"
    return _new_check_result(
        status=status,
        details={
            "used_percent": round(used_percent, 2),
            "threshold_max_used_percent": thresholds.memory_usage_percent_max,
        },
    )


def run_detailed_health_checks(app: Any, thresholds: Optional[HealthThresholds] = None) -> dict[str, Any]:
    thresholds = thresholds or getattr(app.state, "health_thresholds", HealthThresholds())
    if not isinstance(thresholds, HealthThresholds):
        thresholds = HealthThresholds()

    security_settings = getattr(app.state, "security_settings", {}) or {}
    if not isinstance(security_settings, dict):
        security_settings = {}
    secrets_settings = getattr(app.state, "secrets_settings", {}) or {}
    if not isinstance(secrets_settings, dict):
        secrets_settings = {}

    redis_url = None
    rate_limit_cfg = security_settings.get("rate_limit", {})
    if isinstance(rate_limit_cfg, dict):
        redis_url = rate_limit_cfg.get("redis_url")
    if not redis_url:
        redis_url = security_settings.get("rate_limit_redis_url")

    sqlite_db_path = str(security_settings.get("audit_db_path", "audit_trail.db"))
    llm_router = getattr(app.state, "llm_router", None)

    checks = {
        "database": _check_sqlite_connectivity(sqlite_db_path, thresholds.check_timeout_seconds),
        "redis": _check_redis_connectivity(redis_url, thresholds.check_timeout_seconds),
        "llm_providers": _check_llm_providers(llm_router),
        "secrets_manager": _check_secrets_manager_connectivity(
            secrets_settings,
            thresholds.check_timeout_seconds,
        ),
        "disk_space": _check_disk_space(thresholds),
        "memory_usage": _check_memory_usage(thresholds),
    }

    statuses = [item["status"] for item in checks.values()]
    if "failed" in statuses:
        overall = "failed"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "ok"

    return {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "thresholds": asdict(thresholds),
        "checks": checks,
    }


router = APIRouter(tags=["Health"])


@router.get("/health/detailed")
async def detailed_health_check(request: Request) -> dict[str, Any]:
    return run_detailed_health_checks(request.app)


__all__ = [
    "HealthThresholds",
    "load_health_thresholds",
    "run_detailed_health_checks",
    "router",
]
