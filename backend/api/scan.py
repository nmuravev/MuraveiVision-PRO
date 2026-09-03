"""Batch archive video scan API — SSE progress."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services import batch_scanner
from services.security import require_role

router = APIRouter(tags=["scan"])


class ScanStartBody(BaseModel):
    video_path: str = Field(..., min_length=1)
    fps_sample: float = Field(default=1.0, ge=0.1, le=30.0)
    conf: float = Field(default=0.25, ge=0.05, le=0.95)
    save_crops: bool = True
    t_start: float | None = Field(default=None, ge=0)
    t_end: float | None = Field(default=None, ge=0)


@router.get("/api/scan/status")
async def scan_status(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, Any]:
    return batch_scanner.status()


@router.post("/api/scan/start")
async def scan_start(
    body: ScanStartBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        return batch_scanner.start(
            video_path=body.video_path,
            fps_sample=body.fps_sample,
            conf=body.conf,
            save_crops=body.save_crops,
            t_start=body.t_start,
            t_end=body.t_end,
        )
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/scan/stop")
async def scan_stop(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, Any]:
    return batch_scanner.stop()


@router.get("/api/scan/stream")
async def scan_stream(_user: dict[str, Any] = Depends(require_role("operator"))) -> StreamingResponse:
    """SSE progress. Terminal events: done|error only.

    Idle does NOT close the stream (avoids frontend reconnect churn). Clients
    should abort/unsubscribe on done/error; keep-alive comments are sent while idle.
    """

    async def gen():
        idx = 0
        yield f"data: {json.dumps({'type': 'status', **batch_scanner.status()}, ensure_ascii=False)}\n\n"
        while True:
            events, idx = batch_scanner.drain_events(idx)
            for ev in events:
                yield f"data: {json.dumps({'type': 'progress', **ev}, ensure_ascii=False)}\n\n"
                if ev.get("status") in ("done", "error"):
                    return
            st = batch_scanner.status()
            status = st.get("status")
            if status in ("done", "error") and not events:
                yield f"data: {json.dumps({'type': 'status', **st}, ensure_ascii=False)}\n\n"
                return
            if status == "idle" and not events:
                # Keep connection open; ping comment so proxies do not idle-timeout.
                yield ": ping\n\n"
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream")
