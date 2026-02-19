"""
Admin endpoints.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..audit.audit_trail import AuditTrail
from ..dependencies import get_current_admin
from ..models import AuditTrailLogEntry

router = APIRouter(prefix="/admin", tags=["Admin"])


def _get_audit_storage(request: Request) -> AuditTrail:
    storage = getattr(request.app.state, "audit_trail", None)
    if not isinstance(storage, AuditTrail):
        raise HTTPException(status_code=503, detail="Audit storage is not available")
    return storage


@router.get("/audit-logs", response_model=list[AuditTrailLogEntry])
async def get_audit_logs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    user_id: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    resource: Optional[str] = Query(default=None),
    current_admin: dict = Depends(get_current_admin),
):
    """Возвращает audit trail (только для admin)."""
    _ = current_admin
    storage = _get_audit_storage(request)
    rows = storage.list_logs(limit=limit, user_id=user_id, action=action, resource=resource)

    # Пытаемся декодировать details в JSON, если это JSON-строка.
    parsed_rows = []
    for row in rows:
        details = row.get("details")
        if isinstance(details, str):
            try:
                row["details"] = json.loads(details)
            except json.JSONDecodeError:
                pass
        parsed_rows.append(AuditTrailLogEntry(**row))
    return parsed_rows
