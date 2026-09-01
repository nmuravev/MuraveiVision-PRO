"""KML / GeoJSON export endpoints (operator+)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from services import geo_export
from services.security import require_role

router = APIRouter(prefix="/api/export", tags=["export"])


def _safe_filename(source_video: str, ext: str) -> str:
    stem = Path(source_video).name or "export"
    cleaned = "".join(c if c.isalnum() or c in "._-" else "_" for c in stem)[:80]
    return f"muravei_{cleaned}.{ext}"


@router.get("/kml")
async def export_kml(
    source_video: str = Query(..., min_length=1),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> Response:
    try:
        xml = await _to_thread(geo_export.build_kml, source_video)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"kml export failed: {exc}") from exc
    return Response(
        content=xml,
        media_type="application/vnd.google-earth.kml+xml",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(source_video, "kml")}"'},
    )


@router.get("/geojson")
async def export_geojson(
    source_video: str = Query(..., min_length=1),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> Response:
    try:
        data = await _to_thread(geo_export.build_geojson, source_video)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"geojson export failed: {exc}") from exc
    return Response(
        content=json.dumps(data, ensure_ascii=False),
        media_type="application/geo+json",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(source_video, "geojson")}"'},
    )


async def _to_thread(fn, *args):
    import asyncio

    return await asyncio.to_thread(fn, *args)
