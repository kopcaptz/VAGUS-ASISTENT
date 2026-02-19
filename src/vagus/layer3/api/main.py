"""
FastAPI приложение для Vagus Asistent API Gateway.
Основная точка входа для REST API и WebSocket интерфейсов.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vagus.layer1.router import LLMRouter
from vagus.layer2 import create_orchestrator_with_researcher

from .routers import auth, agents, status, tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Инициализация и очистка при старте/завершении приложения."""
    # Инициализация при старте
    app.state.llm_router = LLMRouter()
    await app.state.llm_router.initialize()
    app.state.orchestrator = create_orchestrator_with_researcher(app.state.llm_router)

    yield

    # Очистка при завершении
    if hasattr(app.state.llm_router, "shutdown"):
        await app.state.llm_router.shutdown()


app = FastAPI(
    lifespan=lifespan,
    title="Vagus Asistent API",
    description="API Gateway для Vagus Asistent — оркестрации LLM и агентной системы",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
app.include_router(agents.router, prefix="/api/v1", tags=["agents"])
app.include_router(status.router, prefix="/api/v1", tags=["status"])
