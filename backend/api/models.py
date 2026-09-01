"""Model import API for engineer/master."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from services import model_validator as mv
from services.security import require_role
from services.yolo_engine import WEIGHTS_DIR

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/status")
async def model_status(_user: dict[str, Any] = Depends(require_role("engineer"))) -> dict[str, Any]:
    best = WEIGHTS_DIR / "best.pt"
    backup = WEIGHTS_DIR / "best.pt.backup"
    return {
        "weights_dir": str(WEIGHTS_DIR),
        "best_exists": best.is_file(),
        "best_path": str(best) if best.is_file() else None,
        "backup_exists": backup.is_file(),
        "import": mv.status(),
    }


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
