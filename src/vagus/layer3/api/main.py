"""
FastAPI приложение — точка входа REST API Vagus Asistent.
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .middleware import RateLimitMiddleware
from .routers import agents_router, auth_router, status_router, tasks_router


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения: инициализация и завершение."""
    llm_router, orchestrator = _create_orchestrator()
    await llm_router.initialize()

    app.state.llm_router = llm_router
    app.state.orchestrator = orchestrator
    app.state.start_time = time.monotonic()

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
