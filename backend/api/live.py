"""Live stream control: RTSP/UDP/HTTP → MJPEG for viewers."""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from services.live_stream import get_live_manager
from services.security import ROLE_LEVEL, decode_token, require_role

router = APIRouter(prefix="/api/live", tags=["live"])


class LiveOpenBody(BaseModel):
    viewer_id: str = Field(min_length=1, max_length=32)
    url: str = Field(min_length=3, max_length=2048)


def _token_user(token: str | None) -> dict[str, Any]:
    try:
        user = decode_token(token or "")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="unauthorized") from exc
    if ROLE_LEVEL.get(str(user.get("role", "")), 0) < ROLE_LEVEL["operator"]:
        raise HTTPException(status_code=403, detail="forbidden")
    return user


@router.post("/open")
async def live_open(
    body: LiveOpenBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    mgr = get_live_manager()
    try:
        return mgr.open(body.viewer_id, body.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{viewer_id}")
async def live_close(
    viewer_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return get_live_manager().close(viewer_id)


@router.get("/status")
async def live_status_all(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return {"streams": get_live_manager().list_status()}


@router.get("/{viewer_id}/status")
async def live_status_one(
    viewer_id: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return get_live_manager().status(viewer_id)


@router.get("/{viewer_id}/frame")
async def live_frame(
    viewer_id: str,
    token: str | None = Query(default=None),
) -> Response:
    """Single JPEG (query token for <img> tags without Authorization header)."""
    _token_user(token)
    jpeg = get_live_manager().latest_jpeg(viewer_id)
    if not jpeg:
        raise HTTPException(status_code=404, detail="no frame")
    return Response(content=jpeg, media_type="image/jpeg")


@router.get("/{viewer_id}/mjpeg")
async def live_mjpeg(
    viewer_id: str,
    token: str | None = Query(default=None),
) -> StreamingResponse:
    _token_user(token)
    mgr = get_live_manager()
    if not mgr.status(viewer_id).get("active"):
        raise HTTPException(status_code=404, detail="stream not open")

    boundary = b"frame"

    async def gen():
        last_idx = -1
        idle = 0
        while True:
            st = mgr.status(viewer_id)
            if not st.get("active"):
                break
            jpeg = mgr.latest_jpeg(viewer_id)
            idx = int(st.get("frame_idx") or 0)
            if jpeg and idx != last_idx:
                last_idx = idx
                idle = 0
                yield (
                    b"--" + boundary + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg)).encode("ascii") + b"\r\n\r\n"
                    + jpeg
                    + b"\r\n"
                )
            else:
                idle += 1
                if idle > 200:  # ~10s without frames
                    break
            await asyncio.sleep(0.05)

    return StreamingResponse(
        gen(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary.decode('ascii')}",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
