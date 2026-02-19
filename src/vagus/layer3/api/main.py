"""
FastAPI application — единая точка входа REST API Vagus Asistent.
Lifespan управляет инициализацией и завершением Слоёв 1 и 2.
"""

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from vagus.layer0.logging import get_logger
from vagus.layer1 import LLMRouter
from vagus.layer2 import create_orchestrator_full

from .middleware.logging import RequestLoggingMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .models import TaskStatus
from .routers import agents_router, auth_router, status_router, tasks_router
from .routers.tasks import get_task_store

logger = get_logger("layer3.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: init Layer 1 + Layer 2 on startup, cleanup on shutdown."""
    logger.info("Starting Vagus Asistent API Gateway...")

    llm_router = LLMRouter(
        enable_cache=True,
        enable_budgeting=True,
        enable_monitoring=True,
    )
    await llm_router.initialize()

    orchestrator = create_orchestrator_full(llm_router)

    app.state.llm_router = llm_router
    app.state.orchestrator = orchestrator
    app.state.start_time = time.monotonic()

    logger.info("Vagus Asistent API Gateway is ready.")
    yield

    logger.info("Shutting down Vagus Asistent API Gateway...")


app = FastAPI(
    title="Vagus Asistent API",
    description="Multi-layer AI agent system with LLM routing, orchestration and interfaces.",
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
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)

app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(agents_router, prefix="/api/v1")
app.include_router(status_router, prefix="/api/v1")


@app.websocket("/ws/v1/tasks/{task_id}")
async def stream_task_result(websocket: WebSocket, task_id: str):
    """WebSocket endpoint for real-time task result streaming."""
    await websocket.accept()
    task_store = get_task_store()
    try:
        for _ in range(600):  # up to 5 minutes
            task = task_store.get(task_id)
            if not task:
                await websocket.send_json({"error": "Task not found", "done": True})
                break
            if task["status"] == TaskStatus.COMPLETED:
                result = task.get("result")
                content = result.get("content", str(result)) if isinstance(result, dict) else str(result)
                await websocket.send_json({"content": content, "done": True})
                break
            elif task["status"] == TaskStatus.FAILED:
                await websocket.send_json({
                    "error": task.get("error", "Unknown error"),
                    "done": True,
                })
                break
            else:
                await websocket.send_json({"content": None, "done": False})
                await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass


@app.get("/health")
async def health_check():
    """Simple health check endpoint (no auth required)."""
    return {"status": "ok", "service": "vagus-asistent"}
