"""
FastAPI Dependency Injection.
Provides TaskOrchestrator and current user to route handlers.
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from vagus.layer2.orchestrator import TaskOrchestrator

from .auth import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


def get_orchestrator(request: Request) -> TaskOrchestrator:
    """Dependency: retrieves TaskOrchestrator from application state."""
    return request.app.state.orchestrator


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Dependency: decodes JWT and returns user payload."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    return payload
