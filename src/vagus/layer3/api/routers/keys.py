"""API key management router (admin only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from vagus.security import KeyManager

from ..dependencies import get_current_admin
from ..models import (
    ApiKeyCreateRequest,
    ApiKeyHealthItem,
    ApiKeyListItem,
    ApiKeyListResponse,
    ApiKeysHealthResponse,
    ApiKeyUpdateRequest,
    ApiKeyValidateResponse,
)

router = APIRouter(prefix="/keys", tags=["Keys"])


def _get_key_manager(request: Request, current_admin: dict[str, Any]) -> KeyManager:
    manager = KeyManager()

    def _audit_hook(*, action: str, details: dict[str, Any]) -> None:
        audit = getattr(request.app.state, "audit_trail", None)
        if audit is None:
            return
        ip = request.client.host if request.client else None
        payload = {
            "details": details,
            "by": current_admin.get("sub"),
        }
        audit.log_action(
            user_id=current_admin.get("sub"),
            action=action,
            resource="api_keys",
            details=payload,
            ip_address=ip,
        )

    manager.set_audit_hook(_audit_hook)
    return manager


@router.get("", response_model=ApiKeyListResponse)
async def list_keys(
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> ApiKeyListResponse:
    manager = _get_key_manager(request, current_admin)
    rows = []
    for item in manager.list_keys().values():
        rows.append(
            ApiKeyListItem(
                name=str(item.get("name", "")),
                type=str(item.get("type", "custom")),
                status=str(item.get("status", "active")),
                last_used_at=item.get("last_used_at"),
                created_at=item.get("created_at"),
                masked_value=item.get("masked_value"),
            )
        )
    rows.sort(key=lambda r: r.name)
    return ApiKeyListResponse(keys=rows)


@router.post("", response_model=ApiKeyListItem, status_code=status.HTTP_201_CREATED)
async def create_key(
    payload: ApiKeyCreateRequest,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> ApiKeyListItem:
    manager = _get_key_manager(request, current_admin)
    try:
        created = manager.add_key(
            name=payload.name,
            key_type=payload.type,
            value=payload.value,
            expires_at=payload.expires_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiKeyListItem(
        name=str(created.get("name", payload.name)),
        type=str(created.get("type", payload.type)),
        status=str(created.get("status", "active")),
        last_used_at=created.get("last_used_at"),
        created_at=created.get("created_at"),
        masked_value=created.get("masked_value"),
    )


@router.put("/{key_name}", response_model=ApiKeyListItem)
async def update_key(
    key_name: str,
    payload: ApiKeyUpdateRequest,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> ApiKeyListItem:
    manager = _get_key_manager(request, current_admin)
    try:
        updated = manager.update_key(name=key_name, value=payload.value, expires_at=payload.expires_at)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Key not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiKeyListItem(
        name=str(updated.get("name", key_name)),
        type=str(updated.get("type", "custom")),
        status=str(updated.get("status", "active")),
        last_used_at=updated.get("last_used_at"),
        created_at=updated.get("created_at"),
        masked_value=updated.get("masked_value"),
    )


@router.delete("/{key_name}")
async def delete_key(
    key_name: str,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> dict[str, Any]:
    manager = _get_key_manager(request, current_admin)
    deleted = manager.delete_key(key_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"name": key_name, "deleted": True}


@router.post("/{key_name}/validate", response_model=ApiKeyValidateResponse)
async def validate_key(
    key_name: str,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> ApiKeyValidateResponse:
    manager = _get_key_manager(request, current_admin)
    valid, error = manager.validate_key(key_name, online=True)
    if not valid and error == "Key not found":
        raise HTTPException(status_code=404, detail=error)
    return ApiKeyValidateResponse(valid=valid, error=error)


def _health_payload_to_response(payload: dict[str, Any]) -> ApiKeysHealthResponse:
    key_items = []
    for row in payload.get("keys", []):
        key_items.append(
            ApiKeyHealthItem(
                name=str(row.get("name", "")),
                type=str(row.get("type", "custom")),
                status=str(row.get("status", "unknown")),
                last_validation=row.get("last_validation"),
                expires_in_days=row.get("expires_in_days"),
            )
        )
    return ApiKeysHealthResponse(
        total_keys=int(payload.get("total_keys", 0)),
        valid_keys=int(payload.get("valid_keys", 0)),
        invalid_keys=int(payload.get("invalid_keys", 0)),
        expiring_soon=int(payload.get("expiring_soon", 0)),
        rotation_required=bool(payload.get("rotation_required", False)),
        keys=key_items,
    )


@router.get("/health", response_model=ApiKeysHealthResponse)
async def keys_health(
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> ApiKeysHealthResponse:
    manager = _get_key_manager(request, current_admin)
    return _health_payload_to_response(manager.get_health_stats(days_ahead=7))


@router.post("/health/check", response_model=ApiKeysHealthResponse)
async def run_keys_health_check(
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> ApiKeysHealthResponse:
    manager = _get_key_manager(request, current_admin)
    for key_name in sorted(manager.list_keys().keys()):
        try:
            manager.validate_key(key_name, online=True)
        except Exception:
            continue
    return _health_payload_to_response(manager.get_health_stats(days_ahead=7))
