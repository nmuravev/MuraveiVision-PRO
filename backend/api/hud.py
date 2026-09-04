"""HUD / OSD exclusion zones API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services import hud_exclusion
from services.security import require_role

router = APIRouter(tags=["hud"])


class HudZonesBody(BaseModel):
    video_path: str
    top: float = Field(default=0.0, ge=0.0, le=0.35)
    bottom: float = Field(default=0.0, ge=0.0, le=0.35)
    left: float = Field(default=0.0, ge=0.0, le=0.35)
    right: float = Field(default=0.0, ge=0.0, le=0.35)


class HudRecomputeBody(BaseModel):
    video_path: str
    force: bool = True


@router.get("/api/hud/zones")
async def get_hud_zones(
    video_path: str = Query(...),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    zones = hud_exclusion.ensure_zones_async(video_path)
    return {
        "zones": zones.to_dict(),
        "archive_enabled": hud_exclusion.archive_hud_enabled(),
        "live_enabled": hud_exclusion.live_hud_enabled(),
    }


@router.post("/api/hud/recompute")
async def recompute_hud_zones(
    body: HudRecomputeBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    zones = hud_exclusion.get_zones(body.video_path, force=body.force, wait=True, kickoff=True)
    return {"zones": zones.to_dict()}


@router.put("/api/hud/zones")
async def put_hud_zones(
    body: HudZonesBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        zones = hud_exclusion.save_manual_zones(
            body.video_path,
            top=body.top,
            bottom=body.bottom,
            left=body.left,
            right=body.right,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"zones": zones.to_dict()}
