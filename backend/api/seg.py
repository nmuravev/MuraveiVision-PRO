"""Archive-only segmentation REST. Does not write detections or train."""
from __future__ import annotations

import asyncio
import base64
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.security import require_role
from services.segmentation_engine import DEFAULT_CONF, get_seg_engine

router = APIRouter(prefix="/api/seg", tags=["seg"])

_MISSING = (
    "Сегментация недоступна: нет yolo26n-seg.pt / yolo26s-seg.pt. Детекция без изменений."
)
_NOT_LOADED = (
    "Сегментация: модель не в VRAM. Загрузите через POST /api/seg/load или панель Система."
)


class SegInferRequest(BaseModel):
    image_base64: str | None = None
    confidence: float = Field(default=DEFAULT_CONF, ge=0.05, le=0.99)


class SegLoadRequest(BaseModel):
    weight: str | None = None


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
    try:
        path = await asyncio.to_thread(engine.load_model, name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=_MISSING) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", **engine.status(), "weight": path.name}


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
