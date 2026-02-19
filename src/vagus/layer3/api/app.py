"""
FastAPI application for Vagus Asistent.
Endpoints: /tasks, /auth/token, /auth/refresh, /ws/{task_id}
"""

import time
import uuid
from collections import defaultdict
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from ..auth import AuthService, get_current_user


class TaskCreate(BaseModel):
    prompt: str = Field(..., min_length=1)
    task_type: str = "default"


class TaskResponse(BaseModel):
    task_id: str
    status: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class HealthResponse(BaseModel):
    status: str = "ok"


RATE_LIMIT_MAX = 60
RATE_LIMIT_WINDOW = 60


def create_app(
    auth_service: Optional[AuthService] = None,
    orchestrator: Any = None,
) -> FastAPI:
    app = FastAPI(title="Vagus Asistent API")
    auth = auth_service or AuthService()
    _tasks: dict[str, dict[str, Any]] = {}
    _rate: dict[str, list[float]] = defaultdict(list)
    _ws_connections: dict[str, list[WebSocket]] = defaultdict(list)

    app.state.auth_service = auth
    app.state.orchestrator = orchestrator
    app.state.tasks = _tasks
    app.state.ws_connections = _ws_connections

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    def _check_rate(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - RATE_LIMIT_WINDOW
        _rate[client] = [t for t in _rate[client] if t > window_start]
        if len(_rate[client]) >= RATE_LIMIT_MAX:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        _rate[client].append(now)

    @app.post("/auth/token", response_model=TokenResponse)
    async def login(body: LoginRequest) -> TokenResponse:
        pair = auth.authenticate(body.username, body.password)
        if pair is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad credentials")
        return TokenResponse(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            token_type=pair.token_type,
        )

    @app.post("/auth/refresh", response_model=TokenResponse)
    async def refresh(body: RefreshRequest) -> TokenResponse:
        pair = auth.refresh(body.refresh_token)
        if pair is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        return TokenResponse(
            access_token=pair.access_token,
            refresh_token=pair.refresh_token,
            token_type=pair.token_type,
        )

    @app.post("/tasks", response_model=TaskResponse, status_code=201)
    async def create_task(
        body: TaskCreate,
        request: Request,
        user: str = Depends(get_current_user),
    ) -> TaskResponse:
        _check_rate(request)
        task_id = str(uuid.uuid4())
        _tasks[task_id] = {"status": "pending", "user": user, "prompt": body.prompt, "task_type": body.task_type}

        if orchestrator is not None:
            import asyncio

            async def _run() -> None:
                _tasks[task_id]["status"] = "in_progress"
                for ws in _ws_connections.get(task_id, []):
                    try:
                        await ws.send_json({"task_id": task_id, "status": "in_progress"})
                    except Exception:
                        pass
                result = await orchestrator.execute_task(task_id=task_id, prompt=body.prompt, task_type=body.task_type)
                _tasks[task_id]["status"] = "completed"
                _tasks[task_id]["result"] = result
                for ws in _ws_connections.get(task_id, []):
                    try:
                        await ws.send_json({"task_id": task_id, "status": "completed", "result": result})
                    except Exception:
                        pass

            asyncio.create_task(_run())

        return TaskResponse(task_id=task_id, status="pending")

    @app.get("/tasks/{task_id}", response_model=TaskResponse)
    async def get_task(task_id: str) -> TaskResponse:
        if task_id not in _tasks:
            raise HTTPException(status_code=404, detail="Task not found")
        return TaskResponse(task_id=task_id, status=_tasks[task_id]["status"])

    @app.websocket("/ws/{task_id}")
    async def ws_endpoint(websocket: WebSocket, task_id: str) -> None:
        await websocket.accept()
        _ws_connections[task_id].append(websocket)
        try:
            if task_id in _tasks:
                await websocket.send_json({"task_id": task_id, "status": _tasks[task_id]["status"]})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            _ws_connections[task_id].remove(websocket)

    @app.get("/dashboard/metrics")
    async def dashboard_metrics(user: str = Depends(get_current_user)) -> dict[str, Any]:
        total = len(_tasks)
        completed = sum(1 for t in _tasks.values() if t["status"] == "completed")
        pending = sum(1 for t in _tasks.values() if t["status"] == "pending")
        return {"total_tasks": total, "completed": completed, "pending": pending, "user": user}

    return app


app = create_app()
