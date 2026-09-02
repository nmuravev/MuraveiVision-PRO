"""P3.15: Compare Sync change detection + auto time sync API."""
from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.change_detection import analyze_pair
from services.security import require_role
from services.time_sync import auto_sync

router = APIRouter(prefix="/api/change-detection", tags=["change-detection"])


class ChangeAnalyzeRequest(BaseModel):
    video_before: str
    video_after: str
    time_before: float = Field(ge=0)
    time_after: float = Field(ge=0)
    tolerance_m: float = Field(default=10.0, ge=1.0, le=500.0)
    moved_m: float = Field(default=3.0, ge=0.5, le=100.0)
    time_window_sec: float = Field(default=0.5, ge=0.1, le=10.0)
    use_gps: bool = True
    use_image_fallback: bool = True


class SyncRequest(BaseModel):
    video_before: str
    video_after: str
    source: Literal["auto", "tracks", "detections"] = "auto"
    tolerance_m: float = Field(default=15.0, ge=1.0, le=500.0)


@router.post("/analyze")
async def change_analyze(
    body: ChangeAnalyzeRequest,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            analyze_pair,
            video_before=body.video_before,
            video_after=body.video_after,
            time_before=body.time_before,
            time_after=body.time_after,
            tolerance_m=body.tolerance_m,
            moved_m=body.moved_m,
            time_window_sec=body.time_window_sec,
            use_gps=body.use_gps,
            use_image_fallback=body.use_image_fallback,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sync")
async def sync_videos(
    body: SyncRequest,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(
            auto_sync,
            body.video_before,
            body.video_after,
            source=body.source,
            tolerance_m=body.tolerance_m,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pairs = result.get("pairs") or []
    return {
        "method_used": result.get("method_used", "none"),
        "pairs": pairs[:50],
        "segments": result.get("segments") or [],
        "message": result.get("message"),
        "pair_count_total": int(result.get("pair_count_total") or len(pairs)),
    }
