"""Serve offline map tiles for HTML reports (air-gap)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from services.map_tiles import get_tile_bytes, tiles_available

router = APIRouter(prefix="/api/map", tags=["map"])


@router.get("/tiles/{z}/{x}/{y}.png")
async def map_tile(z: int, x: int, y: int) -> Response:
    if z < 0 or z > 22 or x < 0 or y < 0:
        raise HTTPException(status_code=400, detail="Invalid tile coordinates")
    data = get_tile_bytes(z, x, y)
    if not data:
        raise HTTPException(
            status_code=404,
            detail=(
                "Tile not available offline. Download tiles for this region first. "
                "See docs/ENGINEER_GUIDE.md"
            ),
        )
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/status")
async def map_status() -> dict[str, Any]:
    return {"tiles_available": tiles_available()}
