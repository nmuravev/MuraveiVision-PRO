"""KML / GeoJSON export endpoints (operator+)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from services import geo_export
from services.batch_segmentation import status as batch_seg_status
from services.sam3_propagate import status as sam3_prop_status
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


@router.get("/masks-geotiff")
async def export_masks_geotiff(
    video_path: str = Query(..., min_length=1),
    detection_id: str | None = Query(None),
    time_sec: float | None = Query(None),  # R3 fix: optional time_sec for GPS interpolation
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> Response:
    try:
        from services.export_masks import (
            _check_geo_libs,
            _get_detection_gps,
            build_masks_geotiff,
            resolve_masks_for_video,
        )

        libs_ok, libs_err = _check_geo_libs()
        if not libs_ok:
            raise HTTPException(
                status_code=503,
                detail={"disabled_reason": f"geo_libs_missing: {libs_err}"},
            )

        masks = resolve_masks_for_video(video_path, detection_id, time_sec)
        if not masks:
            raise HTTPException(status_code=404, detail="no masks found for video")

        # H2: None-safe dims chain — never call .get on None
        status_meta = {}
        try:
            status_meta = batch_seg_status() or {}
        except (KeyError, RuntimeError):
            status_meta = {}
        if not status_meta.get("frame_w"):
            try:
                status_meta = sam3_prop_status() or {}
            except (KeyError, RuntimeError):
                status_meta = {}
        frame_w = int(status_meta.get("frame_w") or 1024)
        frame_h = int(status_meta.get("frame_h") or 1024)

        gps = _get_detection_gps(detection_id, video_path, time_sec)
        if not gps:
            # M1: GPS gate with disabled_reason key
            raise HTTPException(
                status_code=400,
                detail={
                    "disabled_reason": "Экспорт GeoTIFF требует GPS. Без GPS доступен только KML."
                },
            )

        tiff_bytes = await asyncio.to_thread(
            build_masks_geotiff, video_path, masks, gps, frame_w, frame_h
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"geotiff export failed: {exc}") from exc

    return Response(
        content=tiff_bytes,
        media_type="image/tiff",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(video_path, "tiff")}"'},
    )


@router.get("/masks-kml")
async def export_masks_kml(
    video_path: str = Query(..., min_length=1),
    detection_id: str | None = Query(None),
    time_sec: float | None = Query(None),  # R3 fix: optional time_sec for GPS interpolation
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> Response:
    try:
        from services.export_masks import (
            _get_detection_gps,
            build_masks_kml,
            resolve_masks_for_video,
        )

        masks = resolve_masks_for_video(video_path, detection_id, time_sec)
        if not masks:
            raise HTTPException(status_code=404, detail="no masks found for video")

        # G-C fix: pass time_sec (parity with geotiff endpoint)
        gps = _get_detection_gps(detection_id, video_path, time_sec)
        xml = await asyncio.to_thread(build_masks_kml, video_path, masks, gps)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"kml export failed: {exc}") from exc

    return Response(
        content=xml,
        media_type="application/vnd.google-earth.kml+xml",
        headers={"Content-Disposition": f'attachment; filename="{_safe_filename(video_path, "kml")}"'},
    )
