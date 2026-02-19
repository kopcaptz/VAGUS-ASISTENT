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
from vagus.monitoring.memory_profiler import MemoryLeakPolicy, MemoryProfiler
from vagus.logging import StructuredLoggingMiddleware, configure_structured_logging

from .audit.audit_trail import AuditTrail
from .auth import configure_jwt_secret_rotation
from .health import health_router, load_health_thresholds
from .middleware import (
    AuditTrailMiddleware,
    IPWhitelistMiddleware,
    RateLimitMiddleware,
    RequestSigningMiddleware,
)
from .metrics import HTTPMetricsMiddleware, metrics_router
from .routers import admin_router, agents_router, auth_router, status_router, tasks_router
from .websocket_security import WebSocketAuditStorage, WebSocketRuntimeSettings

logger = get_logger("layer3.api.main")


def _create_orchestrator():
    """Создаёт полный стек Layer 1 + Layer 2."""
    return _create_orchestrator_with_config({})


def _load_task_timeout_settings(config_data: dict[str, Any]) -> dict[str, float]:
    defaults = {"researcher": 300.0, "coder": 600.0, "analyst": 180.0}
    timeout_cfg = config_data.get("task_timeouts", {}) if isinstance(config_data, dict) else {}
    if not isinstance(timeout_cfg, dict):
        return defaults

    normalized = dict(defaults)
    for key in ("researcher", "coder", "analyst"):
        value = timeout_cfg.get(key)
        if value is None:
            continue
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            normalized[key] = parsed
    return normalized


def _create_orchestrator_with_config(
    runtime_config: dict[str, Any],
    *,
    dead_letter_queue=None,
    error_analytics=None,
    cluster_settings: Optional[dict[str, Any]] = None,
):
    """Создаёт полный стек Layer 1 + Layer 2 с runtime-конфигурацией."""
    from vagus.layer1 import LLMRouter
    from vagus.layer1.integration.config_integration import build_router_kwargs
    from vagus.layer2 import create_orchestrator_full

    router_kwargs = build_router_kwargs(runtime_config)
    llm_router = LLMRouter(**router_kwargs)
    orchestrator = create_orchestrator_full(
        llm_router,
        dead_letter_queue=dead_letter_queue,
        task_timeouts=_load_task_timeout_settings(runtime_config),
        error_analytics=error_analytics,
        cluster_config=cluster_settings,
    )
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

    anonymous_rpm = _safe_int(rate_cfg.get("anonymous_requests_per_minute"), 10)
    user_rpm = _safe_int(rate_cfg.get("user_requests_per_minute"), 100)
    admin_rpm = _safe_int(rate_cfg.get("admin_requests_per_minute"), 1000)
    redis_url = rate_cfg.get("redis_url")

    return {
        "admin_ip_whitelist": _safe_string_list(security_cfg.get("admin_ip_whitelist")),
        "enable_request_signing": _safe_bool(security_cfg.get("enable_request_signing"), False),
        "request_signing_ttl_seconds": _safe_int(
            security_cfg.get("request_signing_ttl_seconds"), 300
        ),
        "request_signing_credentials_path": security_cfg.get("request_signing_credentials_path"),
        "anonymous_requests_per_minute": anonymous_rpm,
        "user_requests_per_minute": user_rpm,
        "admin_requests_per_minute": admin_rpm,
        "rate_limit_redis_url": redis_url,
        "rate_limit": {
            "anonymous_requests_per_minute": anonymous_rpm,
            "user_requests_per_minute": user_rpm,
            "admin_requests_per_minute": admin_rpm,
            "redis_url": redis_url,
        },
        "audit_db_path": security_cfg.get("audit_db_path", "audit_trail.db"),
        "dead_letter_queue_db_path": security_cfg.get(
            "dead_letter_queue_db_path",
            "dead_letter_queue.db",
        ),
        "error_analytics_db_path": security_cfg.get(
            "error_analytics_db_path",
            "error_analytics.db",
        ),
    }


def _load_jwt_settings(config_data: dict[str, Any]) -> dict[str, int]:
    jwt_cfg = config_data.get("jwt", {}) if isinstance(config_data, dict) else {}
    if not isinstance(jwt_cfg, dict):
        jwt_cfg = {}
    return {
        "secret_rotation_days": _safe_int(jwt_cfg.get("secret_rotation_days"), 30),
        "max_old_secrets": _safe_int(jwt_cfg.get("max_old_secrets"), 3),
    }


def _load_secrets_settings(config_data: dict[str, Any]) -> dict[str, Any]:
    secrets_cfg = config_data.get("secrets", {}) if isinstance(config_data, dict) else {}
    if not isinstance(secrets_cfg, dict):
        secrets_cfg = {}
    backend = secrets_cfg.get("backend", "local")
    if not isinstance(backend, str):
        backend = "local"
    return {
        "backend": backend.strip().lower() or "local",
        "vault_addr": secrets_cfg.get("vault_addr"),
        "vault_token": secrets_cfg.get("vault_token"),
    }


def _load_memory_profiler_settings(config_data: dict[str, Any]) -> dict[str, Any]:
    monitoring_cfg = config_data.get("monitoring", {}) if isinstance(config_data, dict) else {}
    if not isinstance(monitoring_cfg, dict):
        monitoring_cfg = {}
    memory_cfg = monitoring_cfg.get("memory_profiler", {})
    if not isinstance(memory_cfg, dict):
        memory_cfg = {}
    return {
        "enabled": _safe_bool(memory_cfg.get("enabled"), True),
        "interval_seconds": _safe_int(memory_cfg.get("interval_seconds"), 30),
        "history_limit": _safe_int(memory_cfg.get("history_limit"), 1024),
        "leak_threshold_mb": float(memory_cfg.get("leak_threshold_mb", 100.0) or 100.0),
        "leak_window_seconds": _safe_int(memory_cfg.get("leak_window_seconds"), 300),
    }


def _load_cluster_settings(config_data: dict[str, Any]) -> dict[str, Any]:
    layer2_cfg = config_data.get("layer2", {}) if isinstance(config_data, dict) else {}
    if not isinstance(layer2_cfg, dict):
        layer2_cfg = {}
    cluster_cfg = layer2_cfg.get("cluster", {})
    if not isinstance(cluster_cfg, dict):
        cluster_cfg = {}
    queue_cfg = cluster_cfg.get("shared_task_queue", {})
    if not isinstance(queue_cfg, dict):
        queue_cfg = {}
    lock_cfg = cluster_cfg.get("distributed_locking", {})
    if not isinstance(lock_cfg, dict):
        lock_cfg = {}
    return {
        "enabled": _safe_bool(cluster_cfg.get("enabled"), False),
        "node_id": str(cluster_cfg.get("node_id", "node-local")),
        "stateless_agents": _safe_bool(cluster_cfg.get("stateless_agents"), True),
        "shared_task_queue": {
            "enabled": _safe_bool(queue_cfg.get("enabled"), False),
            "redis_url": queue_cfg.get("redis_url"),
            "queue_name": queue_cfg.get("queue_name", "vagus:cluster:tasks"),
        },
        "distributed_locking": {
            "enabled": _safe_bool(lock_cfg.get("enabled"), False),
            "redis_url": lock_cfg.get("redis_url"),
            "lock_ttl_seconds": _safe_int(lock_cfg.get("lock_ttl_seconds"), 900),
        },
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения: инициализация и завершение."""
    from vagus.layer2.dead_letter_queue import DeadLetterQueueStorage
    from vagus.layer1.providers.base import LLMProvider
    from vagus.monitoring.error_analytics import ErrorAnalyticsStorage

    runtime_config = getattr(app.state, "runtime_config", {})
    security_settings = getattr(app.state, "security_settings", {})
    dead_letter_queue = DeadLetterQueueStorage(
        str(security_settings.get("dead_letter_queue_db_path", "dead_letter_queue.db"))
    )
    error_analytics = ErrorAnalyticsStorage(
        str(security_settings.get("error_analytics_db_path", "error_analytics.db"))
    )

    llm_router, orchestrator = _create_orchestrator_with_config(
        runtime_config,
        dead_letter_queue=dead_letter_queue,
        error_analytics=error_analytics,
        cluster_settings=getattr(app.state, "cluster_settings", {}),
    )
    await llm_router.initialize()

    app.state.llm_router = llm_router
    app.state.orchestrator = orchestrator
    app.state.dead_letter_queue = dead_letter_queue
    app.state.error_analytics = error_analytics
    app.state.start_time = time.monotonic()
    app.state.websocket_settings = getattr(app.state, "websocket_settings", WebSocketRuntimeSettings())
    audit_db_path = security_settings.get("audit_db_path", "audit_trail.db")
    app.state.audit_trail = AuditTrail(db_path=str(audit_db_path))
    app.state.websocket_audit_storage = WebSocketAuditStorage()
    memory_settings = getattr(app.state, "memory_profiler_settings", {})
    if not isinstance(memory_settings, dict):
        memory_settings = {}
    app.state.memory_profiler = MemoryProfiler(
        leak_policy=MemoryLeakPolicy(
            threshold_mb=float(memory_settings.get("leak_threshold_mb", 100.0)),
            window_seconds=int(memory_settings.get("leak_window_seconds", 300)),
        ),
        history_limit=int(memory_settings.get("history_limit", 1024)),
    )
    if bool(memory_settings.get("enabled", True)):
        await app.state.memory_profiler.start(
            interval_seconds=int(memory_settings.get("interval_seconds", 30))
        )
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

    try:
        if hasattr(app.state, "memory_profiler"):
            await app.state.memory_profiler.stop()
    except Exception as exc:
        logger.warning("Failed to stop memory profiler: %s", exc)
    try:
        if hasattr(llm_router, "cache") and hasattr(llm_router.cache, "close"):
            await llm_router.cache.close()
    except Exception as exc:
        logger.warning("Failed to close cache backends: %s", exc)
    try:
        await LLMProvider.close_shared_http_client()
    except Exception as exc:
        logger.warning("Failed to close shared provider HTTP pool: %s", exc)


def create_app() -> FastAPI:
    """Фабрика приложения FastAPI."""
    configure_structured_logging(force=True)

    runtime_config, runtime_config_path = _load_runtime_yaml_config()
    websocket_settings = _load_websocket_settings(runtime_config)
    security_settings = _load_security_settings(runtime_config)
    jwt_settings = _load_jwt_settings(runtime_config)
    secrets_settings = _load_secrets_settings(runtime_config)
    memory_profiler_settings = _load_memory_profiler_settings(runtime_config)
    cluster_settings = _load_cluster_settings(runtime_config)
    health_thresholds = load_health_thresholds(runtime_config)
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
    app.add_middleware(HTTPMetricsMiddleware)
    app.add_middleware(StructuredLoggingMiddleware, component="api")

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")
    app.include_router(agents_router, prefix="/api/v1")
    app.include_router(status_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(metrics_router)
    app.include_router(health_router)

    app.state.websocket_settings = websocket_settings
    app.state.security_settings = security_settings
    app.state.jwt_settings = jwt_settings
    app.state.secrets_settings = secrets_settings
    app.state.memory_profiler_settings = memory_profiler_settings
    app.state.cluster_settings = cluster_settings
    app.state.health_thresholds = health_thresholds
    app.state.runtime_config = runtime_config

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
