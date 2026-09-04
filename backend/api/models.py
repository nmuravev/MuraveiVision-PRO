"""Model import API for engineer/master."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services import model_validator as mv
from services import usb_models as usb
from services.classes import get_class_catalog
from services.security import require_role
from services.yolo_engine import WEIGHTS_DIR

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/status")
async def model_status(_user: dict[str, Any] = Depends(require_role("engineer"))) -> dict[str, Any]:
    best = WEIGHTS_DIR / "best.pt"
    backup = WEIGHTS_DIR / "best.pt.backup"
    active = None
    try:
        from services.yolo_engine import get_yolo_engine

        active = get_yolo_engine().model_name
    except Exception:  # noqa: BLE001
        active = None
    try:
        n_classes = len(get_class_catalog())
    except Exception:  # noqa: BLE001
        n_classes = 0
    last = usb.last_import_info()
    return {
        "weights_dir": str(WEIGHTS_DIR),
        "best_exists": best.is_file(),
        "best_path": str(best) if best.is_file() else None,
        "backup_exists": backup.is_file(),
        "import": mv.status(),
        "active_model": active,
        "classes_count": n_classes,
        "last_import": last.get("last_import"),
        "last_import_path": last.get("last_import_path"),
    }


class UsbImportBody(BaseModel):
    source_path: str = Field(min_length=1)
    target_type: str = Field(pattern="^(model|classes)$")
    confirm: bool = False


@router.post("/import")
async def model_import(
    file: UploadFile = File(...),
    _user: dict[str, Any] = Depends(require_role("engineer")),
) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".pt"):
        raise HTTPException(status_code=400, detail="Upload a .pt file")
    dest_dir = mv.IMPORT_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"upload_{int(time.time())}.pt"
    data = await file.read()
    if len(data) > mv.MAX_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds {mv.MAX_MB} MB")
    dest.write_bytes(data)
    try:
        return mv.start_import(dest)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/import/stream")
async def model_import_stream(
    _user: dict[str, Any] = Depends(require_role("engineer")),
) -> StreamingResponse:
    async def gen():
        idx = 0
        yield f"data: {json.dumps({'type': 'status', **mv.status()}, ensure_ascii=False)}\n\n"
        while True:
            events, idx = mv.drain_events(idx)
            for ev in events:
                yield f"data: {json.dumps({'type': 'progress', **ev}, ensure_ascii=False)}\n\n"
                if ev.get("status") in ("done", "error", "idle"):
                    return
            st = mv.status()
            if st.get("status") in ("done", "error", "idle") and not events:
                yield f"data: {json.dumps({'type': 'status', **st}, ensure_ascii=False)}\n\n"
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/usb-scan")
async def usb_scan(_user: dict[str, Any] = Depends(require_role("engineer"))) -> dict[str, Any]:
    try:
        return usb.scan_usb()
    except Exception as exc:  # noqa: BLE001
        return {"drives": [], "errors": [str(exc)]}


@router.post("/usb-import")
async def usb_import(
    body: UsbImportBody,
    _user: dict[str, Any] = Depends(require_role("engineer")),
) -> dict[str, Any]:
    src = Path(body.source_path)
    try:
        if not body.confirm:
            return usb.preview_import(src, body.target_type)
        return usb.confirm_import(src, body.target_type)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
