"""Debug panel — SSE stream of backend runtime logs."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from services import runtime_log
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
