"""Media filesystem API confined to archive/."""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any

from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from services.ffmpeg_util import is_video_readable, video_duration_sec
from services.security import archive_root, assert_in_archive, require_role
from services import trash as trash_svc

router = APIRouter(prefix="/api/media", tags=["media"])

MEDIA_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".wav",
    ".mp3",
}


VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _client_archive_path(path: Path) -> str:
    """Expose paths as archive/... (posix) for FE; never absolute host paths."""
    root = archive_root().resolve()
    try:
        rel = path.resolve().relative_to(root)
    except ValueError:
        # Should not happen after assert_in_archive; fall back to name only
        return f"archive/{path.name}"
    rel_s = rel.as_posix()
    if rel_s in ("", "."):
        return "archive"
    return f"archive/{rel_s}"


def _node_for(path: Path) -> dict[str, Any]:
    is_dir = path.is_dir()
    node: dict[str, Any] = {
        "name": path.name or str(path),
        "path": _client_archive_path(path),
        "type": "folder" if is_dir else "file",
    }
    try:
        st = path.stat()
        node["mtime"] = int(st.st_mtime)
        if not is_dir:
            node["size"] = st.st_size
    except OSError:
        node["mtime"] = 0
        if not is_dir:
            node["size"] = 0
    if not is_dir and path.suffix.lower() in VIDEO_SUFFIXES:
        if is_video_readable(path):
            dur = video_duration_sec(path)
            if dur is not None:
                node["duration_sec"] = dur
        else:
            node["broken_container"] = True
    elif not is_dir:
        node.setdefault("size", 0)
    return node


def _build_tree(path: Path, depth: int = 0, max_depth: int = 4) -> dict[str, Any]:
    node = _node_for(path)
    if not path.is_dir() or depth >= max_depth:
        return node
    children: list[dict[str, Any]] = []
    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        node["children"] = []
        return node
    for entry in entries:
        if entry.name.startswith("."):
            continue
        try:
            assert_in_archive(entry)
        except HTTPException:
            continue
        if entry.is_file() and entry.suffix.lower() not in MEDIA_EXTENSIONS:
            continue
        children.append(_build_tree(entry, depth + 1, max_depth))
    node["children"] = children
    return node


@router.get("/tree")
async def media_tree(
    path: str | None = Query(default=None),
    _user: dict[str, Any] = Depends(require_role("operator")),
):
    root = assert_in_archive(path) if path else archive_root()
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)
    tree = _build_tree(root)
    return {"tree": [tree]}


@router.delete("/delete")
async def media_delete(
    path: str = Query(...),
    _user: dict[str, Any] = Depends(require_role("operator")),
):
    """Soft-delete: move into archive/.trash/ (legacy path kept for UI)."""
    return trash_svc.move_to_trash(path)


class TrashBody(BaseModel):
    path: str = Field(..., min_length=1)


@router.post("/trash")
async def media_trash(
    body: TrashBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
):
    return trash_svc.move_to_trash(body.path)


@router.get("/trash")
async def media_trash_list(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return {"items": trash_svc.list_trash()}


@router.post("/restore")
async def media_restore(
    body: TrashBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
):
    """body.path = trash file path under archive/.trash/."""
    return trash_svc.restore_from_trash(body.path)


@router.delete("/permanent")
async def media_permanent(
    path: str = Query(...),
    _user: dict[str, Any] = Depends(require_role("operator")),
):
    return trash_svc.permanent_delete(path)


@router.get("/file")
async def media_file_info(
    path: str = Query(...),
    _user: dict[str, Any] = Depends(require_role("operator")),
):
    target = assert_in_archive(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "name": target.name,
        "path": _client_archive_path(target),
        "size": target.stat().st_size,
        "ext": target.suffix.lower(),
    }


@router.get("/stream")
async def media_stream(
    request: Request,
    path: str = Query(...),
    _user: dict[str, Any] = Depends(require_role("operator")),
):
    target = assert_in_archive(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    media_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    media_type = media_types.get(target.suffix.lower(), "application/octet-stream")
    size = target.stat().st_size
    range_header = request.headers.get("range")
    if range_header and range_header.lower().startswith("bytes="):
        raw = range_header[6:].split(",", 1)[0].strip()
        try:
            start_raw, end_raw = raw.split("-", 1)
            if start_raw:
                start = int(start_raw)
                end = int(end_raw) if end_raw else size - 1
            else:
                suffix = int(end_raw)
                start = max(0, size - suffix)
                end = size - 1
            if start < 0 or start >= size or end < start:
                raise ValueError
            end = min(end, size - 1)
        except (ValueError, TypeError):
            return Response(
                status_code=416,
                headers={"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"},
            )

        length = end - start + 1

        def iter_range():
            remaining = length
            with target.open("rb") as stream:
                stream.seek(start)
                while remaining > 0:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_range(),
            status_code=206,
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Content-Length": str(length),
            },
        )
    return FileResponse(
        target,
        media_type=media_type,
        filename=target.name,
        headers={"Accept-Ranges": "bytes"},
    )


def _extract_filmstrip(video_path: Path, count: int) -> dict[str, Any]:
    if not is_video_readable(video_path):
        return {"duration": None, "frames": [], "broken_container": True}

    # Prefer ffprobe duration (moov-at-end / odd containers); OpenCV for sampling only.
    duration = video_duration_sec(video_path)

    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path.name}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 25.0
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if duration is None or duration <= 0:
        duration = nframes / fps if nframes > 0 else 0.0
    count = max(2, min(int(count), 48))
    frames: list[dict[str, Any]] = []
    if nframes <= 0:
        cap.release()
        return {"duration": duration, "frames": []}
    interval = max(1, nframes // count)
    idx = 0
    while len(frames) < count:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        take = idx % interval == 0 or idx == nframes - 1
        if take:
            h, w = frame.shape[:2]
            nw = 160
            nh = max(1, int(h * nw / max(1, w)))
            small = cv2.resize(frame, (nw, nh))
            encoded, buf = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), 68])
            if encoded:
                b64 = base64.b64encode(buf.tobytes()).decode("ascii")
                frames.append({"t": round(idx / fps, 3), "image": f"data:image/jpeg;base64,{b64}"})
        idx += 1
        if idx >= nframes:
            break
    cap.release()
    return {"duration": duration, "frames": frames}


def _extract_frame_at(video_path: Path, time_sec: float) -> dict[str, Any]:
    import base64

    import cv2

    if not is_video_readable(video_path):
        raise RuntimeError("Видео недоступно или повреждено (moov)")
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path.name}")
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(time_sec)) * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            raise RuntimeError("Не удалось прочитать кадр")
        encoded, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if not encoded:
            raise RuntimeError("JPEG encode failed")
        b64 = base64.b64encode(buf.tobytes()).decode("ascii")
        return {"time_sec": round(float(time_sec), 3), "image_base64": b64}
    finally:
        cap.release()


@router.get("/frame")
async def media_frame(
    path: str = Query(...),
    t: float = Query(default=0.0, ge=0.0),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    target = assert_in_archive(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if target.suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        raise HTTPException(status_code=400, detail="Not a video")
    try:
        payload = await asyncio.to_thread(_extract_frame_at, target, t)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Frame extract failed: {exc}") from exc
    payload["path"] = str(target)
    return payload


@router.get("/filmstrip")
async def media_filmstrip(
    path: str = Query(...),
    count: int = Query(default=40, ge=8, le=80),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    target = assert_in_archive(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if target.suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        raise HTTPException(status_code=400, detail="Not a video")
    try:
        payload = await asyncio.to_thread(_extract_filmstrip, target, count)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Filmstrip failed: {exc}") from exc
    payload["path"] = str(target)
    return payload
