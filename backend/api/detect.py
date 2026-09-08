"""Detection REST + WebSocket endpoints."""
from __future__ import annotations

import base64
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from services.security import ROLE_LEVEL, decode_token, require_role
from services.yolo_engine import get_yolo_engine
from services.db import get_setting

logger = logging.getLogger("muravei.detect")

router = APIRouter(tags=["detect"])


class DetectRequest(BaseModel):
    image_base64: str | None = None
    confidence: float = Field(default=0.5, ge=0.05, le=0.99)
    frame_idx: int = 0
    time_sec: float = 0.0
    use_sahi: bool | None = None
    slice_height: int = Field(default=512, ge=128, le=2048)
    slice_width: int = Field(default=512, ge=128, le=2048)
    overlap_ratio: float = Field(default=0.2, ge=0.0, le=0.5)


def _sahi_default() -> bool:
    """Resolve system-wide SAHI default from SQLite settings (default ON)."""
    try:
        return (get_setting("use_sahi_default") or "1") == "1"
    except Exception:  # noqa: BLE001
        return True


def _resolve_use_sahi(flag: bool | None) -> bool:
    return bool(flag) if flag is not None else _sahi_default()


def _decode_image(raw: str | None) -> bytes:
    if not raw:
        return b""
    data = raw
    if "," in data:
        data = data.split(",", 1)[1]
    return base64.b64decode(data)


@router.post("/api/detect")
async def detect_once(
    body: DetectRequest,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    engine = get_yolo_engine()
    raw = _decode_image(body.image_base64)
    if _resolve_use_sahi(body.use_sahi):
        return await engine.infer_sahi(
            raw, body.confidence, body.frame_idx, body.time_sec,
            slice_height=body.slice_height, slice_width=body.slice_width,
            overlap_ratio=body.overlap_ratio,
        )
    return await engine.infer(raw, body.confidence, body.frame_idx, body.time_sec)


@router.get("/api/detect/status")
async def detect_status(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    """Live engine snapshot for DebugPanel (device, tier, last ms, queue)."""
    engine = get_yolo_engine()
    return engine.status_snapshot()


@router.websocket("/ws/detect/{viewer_id}")
async def detect_ws(websocket: WebSocket, viewer_id: str) -> None:
    token = websocket.query_params.get("token")
    try:
        user = decode_token(token or "")
        if ROLE_LEVEL.get(str(user.get("role", "")), 0) < ROLE_LEVEL["operator"]:
            raise ValueError("forbidden")
    except Exception as exc:  # noqa: BLE001
        logger.warning("WS auth failed for %s: %s", viewer_id, exc)
        await websocket.close(code=4401)
        return

    await websocket.accept()
    engine = get_yolo_engine()
    logger.info("WS detect connected viewer=%s role=%s", viewer_id, user.get("role"))
    try:
        while True:
            message = await websocket.receive_text()
            payload = json.loads(message)
            confidence = float(payload.get("confidence", 0.5))
            frame_idx = int(payload.get("frameIdx", 0))
            time_sec = float(payload.get("timeSec", 0))
            raw = b""
            img = payload.get("image")
            if img:
                raw = _decode_image(img if isinstance(img, str) else None)
            # Optional live HUD mask (default OFF) — needs sourceVideo in payload
            try:
                from services.hud_exclusion import (
                    ensure_zones_async,
                    get_zones,
                    live_hud_enabled,
                    mask_jpeg_bytes,
                )

                src_v = payload.get("sourceVideo") or payload.get("source_video")
                if live_hud_enabled() and src_v and raw:
                    ensure_zones_async(str(src_v))
                    z = get_zones(str(src_v), kickoff=True, wait=False)
                    if z.has_exclusion():
                        raw = mask_jpeg_bytes(raw, z)
            except Exception as hud_exc:  # noqa: BLE001
                logger.debug("live HUD skip: %s", hud_exc)
            use_sahi_flag = payload.get("useSahi")
            if use_sahi_flag is None and payload.get("use_sahi") is not None:
                use_sahi_flag = payload.get("use_sahi")
            if _resolve_use_sahi(use_sahi_flag if isinstance(use_sahi_flag, bool) else None):
                slice_height = int(payload.get("sliceHeight", 512))
                slice_width = int(payload.get("sliceWidth", 512))
                overlap_ratio = float(payload.get("overlapRatio", 0.2))
                result = await engine.infer_sahi(
                    raw, confidence, frame_idx, time_sec, viewer_id=viewer_id,
                    slice_height=slice_height, slice_width=slice_width,
                    overlap_ratio=overlap_ratio,
                )
            else:
                result = await engine.infer(raw, confidence, frame_idx, time_sec, viewer_id=viewer_id)
            result["viewerId"] = viewer_id
            await websocket.send_text(json.dumps(result))
    except WebSocketDisconnect:
        logger.info("WS detect disconnected viewer=%s", viewer_id)
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("WS detect error viewer=%s: %s", viewer_id, exc)
        try:
            await websocket.send_text(json.dumps({"error": str(exc), "mode": engine.mode}))
        except Exception as send_exc:  # noqa: BLE001
            logger.warning("WS detect failed to send error: %s", send_exc)
        try:
            await websocket.close(code=1011)
        except Exception as close_exc:  # noqa: BLE001
            logger.warning("WS detect failed to close: %s", close_exc)
