"""Unified event timeline API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from services.events import list_timeline
from services.security import require_role

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/timeline")
async def get_timeline(
    window: float = Query(default=300, ge=10, le=86400),
    limit: int = Query(default=100, ge=1, le=200),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return {"events": list_timeline(window=window, limit=limit)}
