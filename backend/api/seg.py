"""Archive-only segmentation REST. Does not write detections or train."""
from __future__ import annotations

import asyncio
import base64
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import batch_segmentation
from services import sam3_propagate
from services.security import require_role
from services.sam3_engine import get_sam3_engine
from services.segmentation_engine import DEFAULT_CONF, get_seg_engine

router = APIRouter(prefix="/api/seg", tags=["seg"])

_MISSING = (
    "Сегментация недоступна: нет yolo26n-seg.pt / yolo26s-seg.pt. Детекция без изменений."
)
_NOT_LOADED = (
    "Сегментация: модель не в VRAM. Загрузите через POST /api/seg/load или панель Система."
)
_SAM3_MISSING = "SAM3 недоступен: нет assets/models/sam3.pt. Скопируйте вес офлайн."
_SAM3_NOT_LOADED = "SAM3: модель не в VRAM. Загрузите через POST /api/seg/sam3/load."


class SegInferRequest(BaseModel):
    image_base64: str | None = None
    confidence: float = Field(default=DEFAULT_CONF, ge=0.05, le=0.99)


class SegLoadRequest(BaseModel):
    weight: str | None = None


class BatchSegRequest(BaseModel):
    video_path: str = Field(..., min_length=1)
    frame_step: int = Field(default=30, ge=1, le=300)
    confidence: float = Field(default=0.5, ge=0.05, le=0.99)
    weight: str | None = None


class Sam3LoadRequest(BaseModel):
    weight: str | None = None


class Sam3Point(BaseModel):
    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    label: int = Field(default=1, ge=0, le=1)


class Sam3BBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class Sam3InferRequest(BaseModel):
    image_base64: str | None = None
    points: list[Sam3Point] | None = None
    bboxes: list[Sam3BBox] | None = None
    text: list[str] | None = None


class Sam3PropagateRequest(BaseModel):
    video_path: str = Field(..., min_length=1)
    time_sec: float = Field(..., ge=0.0)
    max_frames: int = Field(default=30, ge=1, le=30)
    points: list[Sam3Point] | None = None
    bboxes: list[Sam3BBox] | None = None
    text: list[str] | None = None
    persist: bool = False


def _decode_image(raw: str | None) -> bytes:
    if not raw:
        return b""
    data = raw
    if "," in data:
        data = data.split(",", 1)[1]
    return base64.b64decode(data)


@router.get("/status")
async def seg_status(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return get_seg_engine().status()


@router.post("/load")
async def seg_load(
    body: SegLoadRequest | None = None,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    engine = get_seg_engine()
    name = (body.weight if body else None) or None
    sam_was = bool(get_sam3_engine().status().get("loaded"))
    try:
        path = await asyncio.to_thread(engine.load_model, name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=_MISSING) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "ok",
        **engine.status(),
        "weight": path.name,
        "sam_unloaded": sam_was,
    }


@router.post("/unload")
async def seg_unload(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    engine = get_seg_engine()
    await asyncio.to_thread(engine.unload_model)
    return {"status": "ok", **engine.status()}


@router.post("/infer")
async def seg_infer(
    body: SegInferRequest,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    engine = get_seg_engine()
    st = engine.status()
    if not st["ready"]:
        raise HTTPException(status_code=503, detail=_MISSING)
    if not st["loaded"]:
        raise HTTPException(status_code=503, detail=_NOT_LOADED)
    try:
        jpeg = _decode_image(body.image_base64)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid image") from exc
    if not jpeg:
        raise HTTPException(status_code=400, detail="image required")
    try:
        return await asyncio.to_thread(engine.infer_jpeg, jpeg, body.confidence)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=_NOT_LOADED) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=_MISSING) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/batch")
async def seg_batch_start(
    body: BatchSegRequest,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(
            lambda: batch_segmentation.start(
                video_path=body.video_path,
                frame_step=body.frame_step,
                confidence=body.confidence,
                weight=body.weight,
            )
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/batch/{task_id}")
async def seg_batch_status(
    task_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(batch_segmentation.status, task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/batch/{task_id}/abort")
async def seg_batch_abort(
    task_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(batch_segmentation.abort, task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/sam3/status")
async def sam3_status(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return get_sam3_engine().status()


@router.post("/sam3/load")
async def sam3_load(
    body: Sam3LoadRequest | None = None,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    engine = get_sam3_engine()
    name = (body.weight if body else None) or None
    yolo_was = bool(get_seg_engine().status().get("loaded"))
    try:
        path = await asyncio.to_thread(engine.load_model, name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=_SAM3_MISSING) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "ok",
        **engine.status(),
        "weight": path.name,
        "yolo_seg_unloaded": yolo_was,
    }


@router.post("/sam3/unload")
async def sam3_unload(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    engine = get_sam3_engine()
    await asyncio.to_thread(engine.unload_model)
    return {"status": "ok", **engine.status()}


@router.post("/sam3/infer")
async def sam3_infer(
    body: Sam3InferRequest,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    engine = get_sam3_engine()
    st = engine.status()
    if not st["ready"]:
        raise HTTPException(status_code=503, detail=_SAM3_MISSING)
    if not st["loaded"]:
        raise HTTPException(status_code=503, detail=_SAM3_NOT_LOADED)
    try:
        jpeg = _decode_image(body.image_base64)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid image") from exc
    if not jpeg:
        raise HTTPException(status_code=400, detail="image required")
    points = [p.model_dump() for p in (body.points or [])]
    bboxes = [b.model_dump() for b in (body.bboxes or [])]
    texts = list(body.text or [])
    has_visual = bool(points or bboxes)
    has_text = bool(any(str(t or "").strip() for t in texts))
    if has_visual == has_text:
        raise HTTPException(
            status_code=400,
            detail="Provide either visual prompts (points/bboxes) OR text, not both/neither",
        )
    try:
        if has_text:
            return await asyncio.to_thread(
                lambda: engine.infer_text(jpeg, texts)
            )
        return await asyncio.to_thread(
            lambda: engine.infer_prompts(jpeg, points_norm=points, bboxes_norm=bboxes)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=_SAM3_NOT_LOADED) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sam3/propagate")
async def sam3_propagate_start(
    body: Sam3PropagateRequest,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    points = [p.model_dump() for p in (body.points or [])]
    bboxes = [b.model_dump() for b in (body.bboxes or [])]
    texts = list(body.text or [])
    has_visual = bool(points or bboxes)
    has_text = bool(any(str(t or "").strip() for t in texts))
    if has_visual == has_text:
        raise HTTPException(
            status_code=400,
            detail="Provide either visual prompts (points/bboxes) OR text, not both/neither",
        )
    try:
        return await asyncio.to_thread(
            lambda: sam3_propagate.start(
                video_path=body.video_path,
                time_sec=body.time_sec,
                max_frames=body.max_frames,
                points=points if has_visual else [],
                bboxes=bboxes if has_visual else [],
                texts=texts if has_text else None,
                persist=body.persist,
            )
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "не в VRAM" in msg or "not loaded" in msg.lower():
            raise HTTPException(status_code=503, detail=_SAM3_NOT_LOADED) from exc
        if "уже выполняется" in msg:
            raise HTTPException(status_code=409, detail=msg) from exc
        raise HTTPException(status_code=503, detail=msg) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=_SAM3_MISSING) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sam3/propagate/{task_id}")
async def sam3_propagate_status(
    task_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(sam3_propagate.status, task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/sam3/propagate/{task_id}/abort")
async def sam3_propagate_abort(
    task_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(sam3_propagate.abort, task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
