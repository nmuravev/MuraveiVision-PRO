"""REC start/stop for operator session capture."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services.recorder import RECORD_ROOT
from services.recorder import recordings_dir
from services.recorder import start as rec_start
from services.recorder import status as rec_status
from services.recorder import stop as rec_stop
from services.security import assert_in_archive, require_role

router = APIRouter(prefix="/api/rec", tags=["rec"])


class RecStartRequest(BaseModel):
    drone_id: str = Field(default="viewer-1")
    source_path: str
    start_sec: float = 0.0


class RecStopRequest(BaseModel):
    drone_id: str = Field(default="viewer-1")


@router.get("/status")
async def rec_status_ep(
    drone_id: str | None = None,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return rec_status(drone_id)


@router.get("/list")
async def rec_list_ep(
    drone_id: str | None = None,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    """List recorded MP4 files under archive/recordings/."""
    root = recordings_dir(drone_id) if drone_id else RECORD_ROOT
    if not root.exists():
        return {"drone_id": drone_id, "files": [], "root": str(root)}
    files: list[dict[str, Any]] = []
    pattern = "*.mp4" if drone_id else "**/*.mp4"
    for path in sorted(root.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        try:
            st = path.stat()
            files.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "bytes": st.st_size,
                    "mtime": st.st_mtime,
                    "drone_id": path.parent.name if path.parent != RECORD_ROOT else drone_id,
                }
            )
        except OSError:
            continue
    return {"drone_id": drone_id, "files": files, "root": str(root)}


@router.post("/start")
async def rec_start_ep(
    body: RecStartRequest,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    source = assert_in_archive(body.source_path)
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Source media not found")
    try:
        return rec_start(body.drone_id, str(source), body.start_sec)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"REC start failed: {exc}") from exc


@router.post("/stop")
async def rec_stop_ep(
    body: RecStopRequest,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return rec_stop(body.drone_id)
