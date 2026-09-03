"""Geo / flight-track API — local SRT/CSV telemetry."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.db import list_detections
from services.security import require_role
from services import telemetry

router = APIRouter(tags=["geo"])


class GeoImportBody(BaseModel):
    video_path: str = Field(..., min_length=1)


class GeoInterpolateBody(BaseModel):
    video_path: str = Field(..., min_length=1)
    time_sec: float = Field(..., ge=0)


def _enrich_detection(row: dict[str, Any], track: list[dict[str, Any]]) -> dict[str, Any]:
    out = dict(row)
    if out.get("gps_lat") is not None and out.get("gps_lon") is not None:
        return out
    pt = telemetry.interpolate(track, float(out.get("time_sec") or 0))
    if not pt:
        return out
    out["gps_lat"] = pt.get("lat")
    out["gps_lon"] = pt.get("lon")
    out["gps_alt"] = pt.get("alt")
    if "yaw" in pt:
        out["gps_yaw"] = pt["yaw"]
    return out


def _detections_for_video(video_path: str, track: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from pathlib import Path

    rows = list_detections(source_video=video_path, include_deleted=False)
    if not rows:
        base = Path(video_path).name
        all_rows = list_detections(include_deleted=False)
        rows = [r for r in all_rows if Path(str(r.get("source_video") or "")).name == base]
    return [_enrich_detection(r, track) for r in rows]


@router.post("/api/geo/import")
async def geo_import(
    body: GeoImportBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        points = telemetry.ensure_track_for_video(body.video_path)
    except HTTPException:
        raise
    except FileNotFoundError:
        points = []
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    try:
        sidecar = telemetry.find_sidecar(body.video_path)
    except (FileNotFoundError, ValueError):
        sidecar = None
    backfilled = telemetry.backfill_detection_gps(body.video_path) if points else 0
    # KEEP: session trace — do not remove without explicit user order
    from services.trace_middleware import pipeline_trace

    pipeline_trace(
        "geo",
        f"import video={body.video_path} points={len(points)} "
        f"sidecar_missing={sidecar is None and not points} backfilled={backfilled}",
    )
    return {
        "video_path": body.video_path,
        "source_file": str(sidecar) if sidecar else None,
        "point_count": len(points),
        "backfilled": backfilled,
        "points": points,
        "sidecar_missing": sidecar is None and not points,
    }


@router.get("/api/geo/track")
async def geo_track_query(
    video_path: str = Query(..., min_length=1),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    """Prefer query form — safe for Windows absolute paths."""
    points = telemetry.load_track_points(video_path)
    return {
        "video_path": video_path,
        "point_count": len(points),
        "points": points,
    }


@router.get("/api/geo/track/{video_path:path}")
async def geo_track(
    video_path: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    points = telemetry.load_track_points(video_path)
    return {
        "video_path": video_path,
        "point_count": len(points),
        "points": points,
    }


@router.get("/api/geo/detections")
async def geo_detections_query(
    video_path: str = Query(..., min_length=1),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    track = telemetry.load_track_points(video_path)
    enriched = _detections_for_video(video_path, track)
    return {
        "video_path": video_path,
        "point_count": len(track),
        "detections": enriched,
        "count": len(enriched),
    }


@router.get("/api/geo/detections/{video_path:path}")
async def geo_detections(
    video_path: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    track = telemetry.load_track_points(video_path)
    enriched = _detections_for_video(video_path, track)
    return {
        "video_path": video_path,
        "point_count": len(track),
        "detections": enriched,
        "count": len(enriched),
    }


@router.post("/api/geo/interpolate")
async def geo_interpolate(
    body: GeoInterpolateBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    track = telemetry.load_track_points(body.video_path)
    pt = telemetry.interpolate(track, body.time_sec)
    if pt is None:
        raise HTTPException(status_code=404, detail="Нет траектории для интерполяции")
    return {
        "video_path": body.video_path,
        "time_sec": body.time_sec,
        "point": pt,
    }
