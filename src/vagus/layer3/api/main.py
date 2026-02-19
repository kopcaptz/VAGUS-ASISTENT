"""
FastAPI приложение — точка входа REST API Vagus Asistent.
"""

import time
from contextlib import asynccontextmanager
from pathlib import Path

import yaml

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vagus.layer0.logging import get_logger

from .middleware import RateLimitMiddleware
from .routers import agents_router, auth_router, status_router, tasks_router
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


def _load_websocket_settings() -> WebSocketRuntimeSettings:
    """
    Loads WebSocket settings from YAML config with defaults fallback.
    """
    settings = WebSocketRuntimeSettings()
    config_candidates = [Path("configs/vagus.yaml"), Path("configs/vagus.yaml.example")]

    for config_path in config_candidates:
        if not config_path.exists():
            continue
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            ws_cfg = data.get("websocket", {}) if isinstance(data, dict) else {}

            settings = WebSocketRuntimeSettings(
                max_message_size_mb=_safe_int(
                    ws_cfg.get("max_message_size_mb"), settings.max_message_size_mb
                ),
                ping_interval_seconds=_safe_int(
                    ws_cfg.get("ping_interval_seconds"), settings.ping_interval_seconds
                ),
                ping_timeout_seconds=_safe_int(
                    ws_cfg.get("ping_timeout_seconds"), settings.ping_timeout_seconds
                ),
                max_messages_per_minute=settings.max_messages_per_minute,
                status_poll_interval_seconds=settings.status_poll_interval_seconds,
            )
            logger.info(
                "Loaded WebSocket settings from %s: size=%sMB, ping=%ss, timeout=%ss",
                config_path,
                settings.max_message_size_mb,
                settings.ping_interval_seconds,
                settings.ping_timeout_seconds,
            )
            return settings
        except Exception as exc:
            logger.warning("Failed to load WebSocket settings from %s: %s", config_path, exc)

    logger.info(
        "Using default WebSocket settings: size=%sMB, ping=%ss, timeout=%ss",
        settings.max_message_size_mb,
        settings.ping_interval_seconds,
        settings.ping_timeout_seconds,
    )
    return settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения: инициализация и завершение."""
    llm_router, orchestrator = _create_orchestrator()
    await llm_router.initialize()

    app.state.llm_router = llm_router
    app.state.orchestrator = orchestrator
    app.state.start_time = time.monotonic()
    app.state.websocket_settings = _load_websocket_settings()
    app.state.websocket_audit_storage = WebSocketAuditStorage()

    yield


def create_app() -> FastAPI:
    """Фабрика приложения FastAPI."""
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
    app.add_middleware(RateLimitMiddleware, max_requests=120, window_seconds=60)

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(tasks_router, prefix="/api/v1")
    app.include_router(agents_router, prefix="/api/v1")
    app.include_router(status_router, prefix="/api/v1")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
