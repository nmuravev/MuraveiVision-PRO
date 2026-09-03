"""Debug panel — SSE stream of backend runtime logs + session trace file."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services import runtime_log
from services import trace_middleware
from services.security import require_role

router = APIRouter(tags=["debug"])


@router.get("/api/debug/recent")
async def debug_recent(
    limit: int = 400,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    rows = runtime_log.recent(max(1, min(limit, 1000)))
    return {"entries": rows, "count": runtime_log.count()}


@router.post("/api/debug/clear")
async def debug_clear(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, str]:
    runtime_log.clear()
    return {"status": "ok"}


@router.get("/api/debug/stream")
async def debug_stream(_user: dict[str, Any] = Depends(require_role("operator"))) -> StreamingResponse:
    async def gen():
        backlog = runtime_log.recent(300)
        for ev in backlog:
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        idx = runtime_log.count()
        while True:
            events, idx = runtime_log.drain(idx)
            for ev in events:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# KEEP: session trace — do not remove without explicit user order
class TraceToggleBody(BaseModel):
    enabled: bool = Field(...)


@router.get("/api/debug/trace/file")
async def debug_trace_file(
    tail: int = Query(50, ge=1, le=500),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    lines = trace_middleware.read_trace_tail(tail)
    return {
        "path": str(trace_middleware.TRACE_LOG),
        "lines": lines,
        "enabled": trace_middleware.is_trace_enabled(),
    }


@router.post("/api/debug/trace/toggle")
async def debug_trace_toggle(
    body: TraceToggleBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    trace_middleware.set_trace_enabled(body.enabled)
    return {"enabled": trace_middleware.is_trace_enabled()}


@router.get("/api/debug/trace/status")
async def debug_trace_status(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return {"enabled": trace_middleware.is_trace_enabled()}
