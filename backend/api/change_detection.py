"""P3.15: Compare Sync change detection + auto time sync + export + batch API."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from services import batch_change_detection as batch_cd
from services.change_detection import analyze_pair
from services.change_export import build_batch_change_html, build_change_html
from services.geo_export import build_change_kml
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


class BatchChangeRequest(BaseModel):
    video_before: str
    video_after: str
    source: Literal["auto", "tracks", "detections"] = "auto"
    pair_stride: int = Field(default=1, ge=1, le=50)
    max_pairs: int = Field(default=50, ge=1, le=200)
    use_image_fallback: bool = False
    tolerance_m: float = Field(default=10.0, ge=1.0, le=500.0)
    moved_m: float = Field(default=3.0, ge=0.5, le=100.0)
    time_window_sec: float = Field(default=0.5, ge=0.1, le=10.0)
    sync_tolerance_m: float = Field(default=15.0, ge=1.0, le=500.0)


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


@router.post("/batch")
async def batch_change_start(
    body: BatchChangeRequest,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            lambda: batch_cd.start(
                video_before=body.video_before,
                video_after=body.video_after,
                source=body.source,
                pair_stride=body.pair_stride,
                max_pairs=body.max_pairs,
                use_image_fallback=body.use_image_fallback,
                tolerance_m=body.tolerance_m,
                moved_m=body.moved_m,
                time_window_sec=body.time_window_sec,
                sync_tolerance_m=body.sync_tolerance_m,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/batch/{task_id}")
async def batch_change_status(
    task_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(batch_cd.status, task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/batch/{task_id}/abort")
async def batch_change_abort(
    task_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(batch_cd.abort, task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _safe_export_name(ext: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"muravei_change_report_{stamp}.{ext}"


@router.get("/batch/{task_id}/export")
async def batch_change_export(
    task_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> Response:
    try:
        st = await asyncio.to_thread(batch_cd.status, task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if st.get("status") != "done":
        raise HTTPException(
            status_code=409,
            detail=f"batch not done (status={st.get('status')})",
        )
    meta = {
        "video_before": st.get("video_before"),
        "video_after": st.get("video_after"),
        "sync_method": st.get("sync_method"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        body = await asyncio.to_thread(
            build_batch_change_html,
            st.get("aggregate"),
            list(st.get("results") or []),
            meta,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"export failed: {exc}") from exc
    filename = _safe_export_name("html").replace("change_report", "batch_change_report")
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(filename).name)
    return Response(
        content=body,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )


@router.get("/export")
async def export_report(
    format: Literal["html", "kml"] = Query("html"),
    video_before: str = Query(..., min_length=1),
    video_after: str = Query(..., min_length=1),
    time_before: float = Query(..., ge=0),
    time_after: float = Query(..., ge=0),
    tolerance_m: float = Query(10.0, ge=1.0, le=500.0),
    moved_m: float = Query(3.0, ge=0.5, le=100.0),
    time_window_sec: float = Query(0.5, ge=0.1, le=10.0),
    use_gps: bool = Query(True),
    use_image_fallback: bool = Query(True),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> Response:
    try:
        result = await asyncio.to_thread(
            analyze_pair,
            video_before=video_before,
            video_after=video_after,
            time_before=time_before,
            time_after=time_after,
            tolerance_m=tolerance_m,
            moved_m=moved_m,
            time_window_sec=time_window_sec,
            use_gps=use_gps,
            use_image_fallback=use_image_fallback,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    meta = {
        "video_before": video_before,
        "video_after": video_after,
        "time_before": time_before,
        "time_after": time_after,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if format == "html":
            body = await asyncio.to_thread(build_change_html, result, meta)
            media = "text/html; charset=utf-8"
            filename = _safe_export_name("html")
        else:
            body = await asyncio.to_thread(build_change_kml, result, meta)
            media = "application/vnd.google-earth.kml+xml"
            filename = _safe_export_name("kml")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"export failed: {exc}") from exc

    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(filename).name)
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{safe}"'},
    )
