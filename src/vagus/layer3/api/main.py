"""
FastAPI приложение — точка входа REST API Vagus Asistent.
"""

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import yaml

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vagus.layer0.logging import get_logger

from .audit.audit_trail import AuditTrail
from .auth import configure_jwt_secret_rotation
from .middleware import (
    AuditTrailMiddleware,
    IPWhitelistMiddleware,
    RateLimitMiddleware,
    RequestSigningMiddleware,
)
from .routers import admin_router, agents_router, auth_router, status_router, tasks_router
from .websocket_security import WebSocketAuditStorage, WebSocketRuntimeSettings

logger = get_logger("layer3.api.main")


def _create_orchestrator():
    """Создаёт полный стек Layer 1 + Layer 2."""
    from vagus.layer1 import LLMRouter
    from vagus.layer2 import create_orchestrator_full

    llm_router = LLMRouter(
        enable_cache=True,
        enable_budgeting=True,
        enable_monitoring=True,
    )
    orchestrator = create_orchestrator_full(llm_router)
    return llm_router, orchestrator


def _safe_int(value, default: int, *, min_value: int = 1) -> int:
    """Converts value to int and enforces lower bound."""
    try:
        parsed = int(value)
        if parsed < min_value:
            return default
        return parsed
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, int):
        return value != 0
    return default


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def _load_runtime_yaml_config() -> tuple[dict[str, Any], Optional[Path]]:
    config_candidates = [Path("configs/vagus.yaml"), Path("configs/vagus.yaml.example")]
    for config_path in config_candidates:
        if not config_path.exists():
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                return data, config_path
        except Exception as exc:
            logger.warning("Failed to load runtime config from %s: %s", config_path, exc)
    return {}, None


def _load_websocket_settings(config_data: dict[str, Any]) -> WebSocketRuntimeSettings:
    """
    Loads WebSocket settings from YAML config with defaults fallback.
    """
    settings = WebSocketRuntimeSettings()
    ws_cfg = config_data.get("websocket", {}) if isinstance(config_data, dict) else {}
    if not isinstance(ws_cfg, dict):
        ws_cfg = {}

    return WebSocketRuntimeSettings(
        max_message_size_mb=_safe_int(
            ws_cfg.get("max_message_size_mb"), settings.max_message_size_mb
        ),
        ping_interval_seconds=_safe_int(
            ws_cfg.get("ping_interval_seconds"), settings.ping_interval_seconds
        ),
        ping_timeout_seconds=_safe_int(
            ws_cfg.get("ping_timeout_seconds"), settings.ping_timeout_seconds
        ),
        max_messages_per_minute=_safe_int(
            ws_cfg.get("max_messages_per_minute"), settings.max_messages_per_minute
        ),
        status_poll_interval_seconds=settings.status_poll_interval_seconds,
    )


def _load_security_settings(config_data: dict[str, Any]) -> dict[str, Any]:
    security_cfg = config_data.get("security", {}) if isinstance(config_data, dict) else {}
    if not isinstance(security_cfg, dict):
        security_cfg = {}
    rate_cfg = security_cfg.get("rate_limit", {})
    if not isinstance(rate_cfg, dict):
        rate_cfg = {}

    return {
        "admin_ip_whitelist": _safe_string_list(security_cfg.get("admin_ip_whitelist")),
        "enable_request_signing": _safe_bool(security_cfg.get("enable_request_signing"), False),
        "request_signing_ttl_seconds": _safe_int(
            security_cfg.get("request_signing_ttl_seconds"), 300
        ),
        "request_signing_credentials_path": security_cfg.get("request_signing_credentials_path"),
        "anonymous_requests_per_minute": _safe_int(
            rate_cfg.get("anonymous_requests_per_minute"), 10
        ),
        "user_requests_per_minute": _safe_int(rate_cfg.get("user_requests_per_minute"), 100),
        "admin_requests_per_minute": _safe_int(rate_cfg.get("admin_requests_per_minute"), 1000),
        "rate_limit_redis_url": rate_cfg.get("redis_url"),
        "audit_db_path": security_cfg.get("audit_db_path", "audit_trail.db"),
    }


def _load_jwt_settings(config_data: dict[str, Any]) -> dict[str, int]:
    jwt_cfg = config_data.get("jwt", {}) if isinstance(config_data, dict) else {}
    if not isinstance(jwt_cfg, dict):
        jwt_cfg = {}
    return {
        "secret_rotation_days": _safe_int(jwt_cfg.get("secret_rotation_days"), 30),
        "max_old_secrets": _safe_int(jwt_cfg.get("max_old_secrets"), 3),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения: инициализация и завершение."""
    llm_router, orchestrator = _create_orchestrator()
    await llm_router.initialize()

    app.state.llm_router = llm_router
    app.state.orchestrator = orchestrator
    app.state.start_time = time.monotonic()
    app.state.websocket_settings = getattr(app.state, "websocket_settings", WebSocketRuntimeSettings())
    security_settings = getattr(app.state, "security_settings", {})
    audit_db_path = security_settings.get("audit_db_path", "audit_trail.db")
    app.state.audit_trail = AuditTrail(db_path=str(audit_db_path))
    app.state.websocket_audit_storage = WebSocketAuditStorage()
    app.state.audit_trail.log_action(
        user_id="system",
        action="config.loaded",
        resource="runtime",
        details={
            "websocket": {
                "max_message_size_mb": app.state.websocket_settings.max_message_size_mb,
                "ping_interval_seconds": app.state.websocket_settings.ping_interval_seconds,
                "ping_timeout_seconds": app.state.websocket_settings.ping_timeout_seconds,
                "max_messages_per_minute": app.state.websocket_settings.max_messages_per_minute,
            },
            "security": security_settings,
        },
        ip_address="127.0.0.1",
    )

    yield


def create_app() -> FastAPI:
    """Фабрика приложения FastAPI."""
    runtime_config, runtime_config_path = _load_runtime_yaml_config()
    websocket_settings = _load_websocket_settings(runtime_config)
    security_settings = _load_security_settings(runtime_config)
    jwt_settings = _load_jwt_settings(runtime_config)
    configure_jwt_secret_rotation(
        secret_rotation_days=jwt_settings["secret_rotation_days"],
        max_old_secrets=jwt_settings["max_old_secrets"],
    )

    logger.info(
        "Runtime config loaded from %s. Request signing: %s, admin whitelist entries: %s",
        runtime_config_path or "defaults",
        security_settings["enable_request_signing"],
        len(security_settings["admin_ip_whitelist"]),
    )

    app = FastAPI(
        title="Vagus Asistent API",
        description="Multi-layer AI agent system with LLM routing",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8501", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        RateLimitMiddleware,
        window_seconds=60,
        anonymous_requests_per_minute=security_settings["anonymous_requests_per_minute"],
        user_requests_per_minute=security_settings["user_requests_per_minute"],
        admin_requests_per_minute=security_settings["admin_requests_per_minute"],
        redis_url=security_settings["rate_limit_redis_url"],
    )
    app.add_middleware(
        RequestSigningMiddleware,
        enabled=security_settings["enable_request_signing"],
        credentials_path=security_settings["request_signing_credentials_path"],
        timestamp_ttl_seconds=security_settings["request_signing_ttl_seconds"],
    )
    app.add_middleware(
        IPWhitelistMiddleware,
        whitelist=security_settings["admin_ip_whitelist"],
        admin_path_prefix="/api/v1/admin/",
    )
    app.add_middleware(AuditTrailMiddleware)

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")
    app.include_router(agents_router, prefix="/api/v1")
    app.include_router(status_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")

    app.state.websocket_settings = websocket_settings
    app.state.security_settings = security_settings
    app.state.jwt_settings = jwt_settings

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
