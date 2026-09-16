"""CRUD for operator-edited detections stored in SQLite."""
from __future__ import annotations

import base64
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from services.classes import get_class_catalog, ui_name_by_index
from services.db import (
    archive_media_exists,
    get_detection,
    insert_detection,
    list_detections,
    normalize_media_path,
    save_crop_jpeg,
    soft_delete_detection,
    soft_delete_detections_for_source,
    update_detection,
)
from services.export_csv import generate_detections_csv
from services.security import require_role, resolve_under_archive
from services.telemetry import attach_gps

router = APIRouter(prefix="/api/detections", tags=["detections"])


class BBoxNorm(BaseModel):
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)


class DetectionIn(BaseModel):
    id: str | None = None
    source_video: str
    time_sec: float = 0.0
    frame_idx: int = 0
    class_id: int = 0
    class_name: str | None = None
    confidence: float = 1.0
    bbox: BBoxNorm
    user_notes: str = ""
    origin: str = "manual"
    frame_jpeg: str | None = None


class DetectionPatch(BaseModel):
    class_id: int | None = None
    class_name: str | None = None
    confidence: float | None = None
    bbox: BBoxNorm | None = None
    user_notes: str | None = None
    frame_jpeg: str | None = None


class CommitObject(BaseModel):
    class_id: int = 0
    class_name: str | None = None
    confidence: float = 0.5
    bbox: BBoxNorm


class CommitRequest(BaseModel):
    source_video: str
    time_sec: float = 0.0
    frame_idx: int = 0
    frame_jpeg: str | None = None
    objects: list[CommitObject] = Field(default_factory=list)


def _decode_jpeg(data: str | None) -> bytes:
    if not data:
        return b""
    raw = data
    if "," in raw:
        raw = raw.split(",", 1)[1]
    return base64.b64decode(raw)


IOU_MATCH = 0.45
TIME_EPS = 0.35


def _xywh(bbox: BBoxNorm) -> tuple[float, float, float, float]:
    x1, y1 = min(bbox.x1, bbox.x2), min(bbox.y1, bbox.y2)
    x2, y2 = max(bbox.x1, bbox.x2), max(bbox.y1, bbox.y2)
    return x1, y1, max(0.01, x2 - x1), max(0.01, y2 - y1)


def _iou_xywh(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix1, iy1 = max(ax, bx), max(ay, by)
    ix2, iy2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _matches_existing(
    source_video: str,
    time_sec: float,
    xywh: tuple[float, float, float, float],
    existing: list[dict[str, Any]],
) -> dict[str, Any] | None:
    src = normalize_media_path(source_video)
    for row in existing:
        if normalize_media_path(str(row.get("source_video") or "")) != src:
            continue
        if abs(float(row["time_sec"]) - float(time_sec)) > TIME_EPS:
            continue
        other = (
            float(row["bbox_x"]),
            float(row["bbox_y"]),
            float(row["bbox_w"]),
            float(row["bbox_h"]),
        )
        if _iou_xywh(xywh, other) >= IOU_MATCH:
            return row
    return None


def _resolve_name(class_id: int, class_name: str | None) -> str:
    if class_name:
        return class_name
    return ui_name_by_index(class_id)


@router.get("/classes")
async def detection_classes(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return {"classes": get_class_catalog()}


class FindSimilarBody(BaseModel):
    detection_id: str
    top_k: int = Field(default=12, ge=1, le=50)
    same_class: bool = True


@router.post("/find-similar")
async def detections_find_similar(
    body: FindSimilarBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    from services.similarity import find_similar

    try:
        return find_similar(body.detection_id, top_k=body.top_k, same_class=body.same_class)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
async def detections_list(
    source_video: str | None = Query(default=None),
    class_name: str | None = Query(default=None),
    q: str | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    all_videos: bool = Query(
        default=False,
        description="Internal/admin only — return all videos. UI must not use this.",
    ),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    # Empty-by-default: protect UI from loading entire DB (Inspector remount mash).
    if not source_video and not all_videos:
        return {"detections": []}
    if source_video and not all_videos:
        key = normalize_media_path(source_video)
        if not key or not archive_media_exists(key):
            return {"detections": []}
        rows = list_detections(key, class_name, q, include_deleted)
        return {"detections": rows}
    # all_videos=true — for tooling; trainer/reporter use db.list_detections directly
    rows = list_detections(None, class_name, q, include_deleted)
    return {"detections": rows}


@router.get("/export")
async def detections_export_csv(
    source_video: str = Query(..., min_length=1),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> Response:
    key = normalize_media_path(source_video)
    if not key:
        raise HTTPException(status_code=400, detail="source_video required")
    csv_content = generate_detections_csv(key)
    safe_name = key.replace("/", "_").replace("\\", "_")
    filename = f"detections_{safe_name}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("")
async def detections_delete_all_for_source(
    source_video: str = Query(..., min_length=1),
    clear_all: bool = Query(default=False, alias="all"),
    user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    if not clear_all:
        raise HTTPException(status_code=400, detail="Pass all=true to soft-delete by source_video")
    key = normalize_media_path(source_video)
    if not key:
        raise HTTPException(status_code=400, detail="source_video required")
    n = soft_delete_detections_for_source(key, str(user.get("role")))
    return {"ok": True, "deleted": n, "source_video": key}


@router.post("")
async def detections_create(
    body: DetectionIn,
    user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    x, y, w, h = _xywh(body.bbox)
    class_name = _resolve_name(body.class_id, body.class_name)
    source_video = normalize_media_path(body.source_video)
    row = insert_detection(
        attach_gps(
            {
                "id": body.id,
                "source_video": source_video,
                "time_sec": body.time_sec,
                "frame_idx": body.frame_idx,
                "class_id": body.class_id,
                "class_name": class_name,
                "confidence": body.confidence,
                "bbox_x": x,
                "bbox_y": y,
                "bbox_w": w,
                "bbox_h": h,
                "is_edited": 1,
                "edited_by": user.get("role"),
                "edited_at": time.time(),
                "user_notes": body.user_notes,
                "origin": body.origin if body.origin in {"auto", "manual", "batch_scan"} else "manual",
            }
        )
    )
    jpeg = _decode_jpeg(body.frame_jpeg)
    if jpeg:
        crop_path = save_crop_jpeg(
            row["id"], jpeg, {"x": x, "y": y, "w": w, "h": h}
        )
        if crop_path:
            row = update_detection(row["id"], {"crop_path": crop_path}) or row
    return row


@router.post("/commit")
async def detections_commit(
    body: CommitRequest,
    user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    jpeg = _decode_jpeg(body.frame_jpeg)
    source_video = normalize_media_path(body.source_video)
    existing = list_detections(source_video, include_deleted=True)
    created: list[dict[str, Any]] = []
    skipped = 0
    for obj in body.objects:
        x, y, w, h = _xywh(obj.bbox)
        hit = _matches_existing(source_video, body.time_sec, (x, y, w, h), existing)
        if hit:
            skipped += 1
            continue
        class_name = _resolve_name(obj.class_id, obj.class_name)
        row = insert_detection(
            attach_gps(
                {
                    "source_video": source_video,
                    "time_sec": body.time_sec,
                    "frame_idx": body.frame_idx,
                    "class_id": obj.class_id,
                    "class_name": class_name,
                    "ai_class_name": class_name,
                    "confidence": obj.confidence,
                    "bbox_x": x,
                    "bbox_y": y,
                    "bbox_w": w,
                    "bbox_h": h,
                    "is_edited": 0,
                    "origin": "auto",
                }
            )
        )
        if jpeg:
            crop_path = save_crop_jpeg(
                row["id"], jpeg, {"x": x, "y": y, "w": w, "h": h}
            )
            if crop_path:
                row = update_detection(row["id"], {"crop_path": crop_path}) or row
        created.append(row)
        existing.append(row)
    return {
        "detections": created,
        "count": len(created),
        "skipped": skipped,
        "committed_by": user.get("role"),
    }


@router.patch("/{det_id}")
async def detections_patch(
    det_id: str,
    body: DetectionPatch,
    user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    current = get_detection(det_id)
    if not current:
        raise HTTPException(status_code=404, detail="Not found")
    fields: dict[str, Any] = {
        "is_edited": 1,
        "edited_by": user.get("role"),
        "edited_at": time.time(),
    }
    if body.class_id is not None:
        fields["class_id"] = body.class_id
        fields["class_name"] = body.class_name or ui_name_by_index(body.class_id)
        prev_ai = str(current.get("ai_class_name") or current.get("class_name") or "")
        prev_op = str(current.get("class_name") or "")
        if prev_ai == prev_op:
            fields["ai_class_name"] = prev_op
    elif body.class_name is not None:
        fields["class_name"] = body.class_name
        prev_ai = str(current.get("ai_class_name") or current.get("class_name") or "")
        prev_op = str(current.get("class_name") or "")
        if prev_ai == prev_op:
            fields["ai_class_name"] = prev_op
    if body.confidence is not None:
        fields["confidence"] = body.confidence
    if body.user_notes is not None:
        fields["user_notes"] = body.user_notes
    bbox_xywh = None
    if body.bbox is not None:
        x, y, w, h = _xywh(body.bbox)
        fields.update({"bbox_x": x, "bbox_y": y, "bbox_w": w, "bbox_h": h})
        bbox_xywh = {"x": x, "y": y, "w": w, "h": h}
    jpeg = _decode_jpeg(body.frame_jpeg)
    if jpeg:
        crop_path = save_crop_jpeg(
            det_id,
            jpeg,
            bbox_xywh
            or {
                "x": current["bbox_x"],
                "y": current["bbox_y"],
                "w": current["bbox_w"],
                "h": current["bbox_h"],
            },
        )
        if crop_path:
            fields["crop_path"] = crop_path
    updated = update_detection(det_id, fields)
    if not updated:
        raise HTTPException(status_code=404, detail="Not found")
    return updated


@router.get("/{det_id}")
async def detections_get(
    det_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    row = get_detection(det_id)
    if not row or row.get("is_deleted"):
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.delete("/{det_id}")
async def detections_delete(
    det_id: str,
    user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    updated = soft_delete_detection(det_id, str(user.get("role")))
    if not updated:
        raise HTTPException(status_code=404, detail="Not found")
    return updated


@router.get("/{det_id}/crop")
async def detections_crop(
    det_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
):
    row = get_detection(det_id)
    candidates: list[str] = []
    if row and row.get("crop_path"):
        candidates.append(str(row["crop_path"]))
    candidates.append(f"crops/{det_id}.jpg")
    path = None
    for cand in candidates:
        try:
            p = resolve_under_archive(cand)
        except HTTPException:
            continue
        if p.is_file():
            path = p
            break
    if path is None:
        raise HTTPException(status_code=404, detail="Crop not found")
    return FileResponse(path, media_type="image/jpeg")
