"""P3.13.3b: short forward SAM3 video propagate (≤30 frames).

Uses Ultralytics SAM3VideoPredictor on a temp clip. Optional seg_masks SQLite.
Does not write detections / train. Detect ≠ YOLO-seg ≠ SAM3.
"""
from __future__ import annotations

import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from services.sam3_engine import (
    _empty_cache,
    _masks_from_sam_results,
    _unload_yolo_seg,
    get_sam3_engine,
    mask_to_polygon_norm,
    resolve_named_weight,
)

MAX_PROPAGATE_FRAMES = 30

_lock = threading.Lock()
_abort = threading.Event()
_thread: threading.Thread | None = None

_state: dict[str, Any] = {
    "task_id": None,
    "status": "idle",  # idle|running|done|error|aborted
    "progress": 0.0,
    "processed": 0,
    "sample_total": 0,
    "mask_total": 0,
    "persisted": 0,
    "message": "",
    "error": None,
    "video_path": None,
    "max_frames": MAX_PROPAGATE_FRAMES,
    "persist": False,
    "results": [],
}


def _snapshot(*, include_results: bool = False) -> dict[str, Any]:
    with _lock:
        out = {
            "task_id": _state["task_id"],
            "status": _state["status"],
            "progress": float(_state["progress"]),
            "processed": int(_state["processed"]),
            "sample_total": int(_state["sample_total"]),
            "mask_total": int(_state["mask_total"]),
            "persisted": int(_state["persisted"]),
            "message": _state["message"],
            "error": _state["error"],
            "video_path": _state["video_path"],
            "max_frames": int(_state["max_frames"]),
            "persist": bool(_state["persist"]),
        }
        if include_results or _state["status"] in ("done", "aborted", "error"):
            out["results"] = list(_state["results"])
        else:
            out["results"] = None
        return out


def status(task_id: str | None = None) -> dict[str, Any]:
    with _lock:
        current = _state["task_id"]
        terminal = _state["status"] in ("done", "aborted", "error")
    if task_id is not None and current is not None and task_id != current:
        raise KeyError(f"unknown task_id: {task_id}")
    if task_id is not None and current is None:
        raise KeyError(f"unknown task_id: {task_id}")
    return _snapshot(include_results=terminal)


def _set(**kwargs: Any) -> None:
    with _lock:
        for k, v in kwargs.items():
            if k in _state:
                _state[k] = v


def _resolve_video(video_path: str) -> tuple[Path, str]:
    from services.batch_scanner import _resolve_video as resolve

    return resolve(video_path)


def polygon_aabb_norm(polygon: list[list[float]]) -> dict[str, float] | None:
    if not polygon or len(polygon) < 3:
        return None
    xs = [float(p[0]) for p in polygon if len(p) >= 2]
    ys = [float(p[1]) for p in polygon if len(p) >= 2]
    if not xs or not ys:
        return None
    return {
        "x1": max(0.0, min(1.0, min(xs))),
        "y1": max(0.0, min(1.0, min(ys))),
        "x2": max(0.0, min(1.0, max(xs))),
        "y2": max(0.0, min(1.0, max(ys))),
    }


def _norm_bboxes_to_px(
    bboxes_norm: list[dict[str, Any]], w: int, h: int
) -> list[list[float]]:
    boxes: list[list[float]] = []
    for b in bboxes_norm:
        x1 = float(b.get("x1", 0.0)) * w
        y1 = float(b.get("y1", 0.0)) * h
        x2 = float(b.get("x2", 0.0)) * w
        y2 = float(b.get("y2", 0.0)) * h
        boxes.append([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)])
    return boxes


def _seed_bboxes_norm(
    *,
    video_abs: Path,
    start_frame: int,
    points_norm: list[dict[str, Any]],
    bboxes_norm: list[dict[str, Any]],
) -> list[dict[str, float]]:
    if bboxes_norm:
        return [
            {
                "x1": float(b.get("x1", 0.0)),
                "y1": float(b.get("y1", 0.0)),
                "x2": float(b.get("x2", 0.0)),
                "y2": float(b.get("y2", 0.0)),
            }
            for b in bboxes_norm
        ]

    # Points only → image infer → AABB of first mask
    cap = cv2.VideoCapture(str(video_abs))
    try:
        if not cap.isOpened():
            raise RuntimeError(f"Не удалось открыть видео: {video_abs.name}")
        cap.set(cv2.CAP_PROP_POS_FRAMES, float(start_frame))
        ok, frame = cap.read()
        if not ok or frame is None:
            raise ValueError("не удалось прочитать кадр для seed")
        ok_jpg, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not ok_jpg:
            raise ValueError("jpeg encode failed")
        out = get_sam3_engine().infer_prompts(
            buf.tobytes(), points_norm=points_norm, bboxes_norm=[]
        )
        masks = list(out.get("masks") or [])
        if not masks:
            raise ValueError("SAM3 не дал маску для seed из точек")
        aabb = polygon_aabb_norm(masks[0].get("polygon_norm") or [])
        if aabb is None:
            raise ValueError("пустой polygon для seed AABB")
        # Expand slightly so VideoPredictor has room
        pad = 0.01
        return [
            {
                "x1": max(0.0, aabb["x1"] - pad),
                "y1": max(0.0, aabb["y1"] - pad),
                "x2": min(1.0, aabb["x2"] + pad),
                "y2": min(1.0, aabb["y2"] + pad),
            }
        ]
    finally:
        cap.release()


def _write_temp_clip(
    video_abs: Path, start_frame: int, max_frames: int
) -> tuple[Path, float, int, int, int]:
    """Write ≤max_frames from start_frame. Returns (clip, fps, w, h, written)."""
    cap = cv2.VideoCapture(str(video_abs))
    if not cap.isOpened():
        raise RuntimeError(f"Не удалось открыть видео: {video_abs.name}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        if fps <= 0:
            fps = 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        if w < 1 or h < 1:
            raise RuntimeError("invalid video size")

        tmp = Path(tempfile.mkdtemp(prefix="sam3prop_")) / "clip.mp4"
        # mp4v is widely available via OpenCV builds
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(tmp), fourcc, fps, (w, h))
        if not writer.isOpened():
            raise RuntimeError("VideoWriter failed")

        written = 0
        try:
            for i in range(max_frames):
                if _abort.is_set():
                    break
                idx = start_frame + i
                if total > 0 and idx >= total:
                    break
                cap.set(cv2.CAP_PROP_POS_FRAMES, float(idx))
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                if frame.shape[1] != w or frame.shape[0] != h:
                    frame = cv2.resize(frame, (w, h))
                writer.write(frame)
                written += 1
        finally:
            writer.release()

        if written < 1:
            raise ValueError("не удалось записать temp clip")
        return tmp, fps, w, h, written
    finally:
        cap.release()


def _run_video_predictor(
    clip_path: Path, weight_path: Path, bboxes_px: list[list[float]]
) -> list[Any]:
    from ultralytics.models.sam import SAM3VideoPredictor

    predictor = SAM3VideoPredictor(
        overrides={
            "conf": 0.25,
            "task": "segment",
            "mode": "predict",
            "model": str(weight_path),
            "verbose": False,
        }
    )
    stream = predictor(source=str(clip_path), bboxes=bboxes_px, stream=True)
    return list(stream)


def _results_to_frame_masks(result: Any, h: int, w: int) -> list[dict[str, Any]]:
    masks = _masks_from_sam_results([result], h, w)
    if masks:
        return masks
    # Fallback: raw masks tensor
    blob = getattr(result, "masks", None)
    if blob is None:
        return []
    data = getattr(blob, "data", None)
    if data is None:
        return []
    if hasattr(data, "cpu"):
        data = data.cpu().numpy()
    arr = np.asarray(data)
    if arr.ndim == 2:
        arr = arr[None, ...]
    out: list[dict[str, Any]] = []
    for i in range(arr.shape[0]):
        poly = mask_to_polygon_norm(arr[i])
        if len(poly) >= 3:
            out.append({"class": "object", "conf": 1.0, "polygon_norm": poly})
    return out


def _persist_results(
    *,
    source_video: str,
    track_id: str,
    results: list[dict[str, Any]],
) -> int:
    from services import db as dbmod

    rows: list[dict[str, Any]] = []
    for fr in results:
        for m in fr.get("masks") or []:
            rows.append(
                {
                    "source_video": source_video,
                    "time_sec": fr.get("time_sec", 0.0),
                    "frame_idx": fr.get("frame_idx", 0),
                    "class_name": m.get("class") or "object",
                    "confidence": float(m.get("conf") if m.get("conf") is not None else 1.0),
                    "polygon_norm": m.get("polygon_norm") or [],
                    "origin": "sam3",
                    "track_id": track_id,
                }
            )
    if not rows:
        return 0
    return dbmod.insert_seg_masks_batch(rows)


def _run(
    task_id: str,
    video_abs: Path,
    source_key: str,
    time_sec: float,
    max_frames: int,
    points_norm: list[dict[str, Any]],
    bboxes_norm: list[dict[str, Any]],
    persist: bool,
) -> None:
    clip_path: Path | None = None
    clip_dir: Path | None = None
    results: list[dict[str, Any]] = []
    mask_total = 0
    persisted = 0

    try:
        _unload_yolo_seg()
        engine = get_sam3_engine()
        st = engine.status()
        if not st.get("ready"):
            raise FileNotFoundError("SAM3 weight missing")
        if not st.get("loaded"):
            raise RuntimeError("SAM3 model not loaded")

        weight_path = resolve_named_weight(st.get("weight") or "sam3.pt")

        cap = cv2.VideoCapture(str(video_abs))
        if not cap.isOpened():
            raise RuntimeError(f"Не удалось открыть видео: {video_abs.name}")
        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
            if fps <= 0:
                fps = 25.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        finally:
            cap.release()

        start_frame = max(0, int(round(float(time_sec) * fps)))
        if total > 0:
            start_frame = min(start_frame, max(0, total - 1))

        seed_boxes = _seed_bboxes_norm(
            video_abs=video_abs,
            start_frame=start_frame,
            points_norm=points_norm,
            bboxes_norm=bboxes_norm,
        )

        clip_path, clip_fps, w, h, written = _write_temp_clip(
            video_abs, start_frame, max_frames
        )
        clip_dir = clip_path.parent
        _set(
            sample_total=written,
            message=f"Propagate {written} кадров с t={time_sec:.2f}с",
            progress=0.05,
        )

        if _abort.is_set():
            _set(
                status="aborted",
                message="Propagate прерван",
                results=[],
                processed=0,
                mask_total=0,
                progress=0.0,
            )
            return

        bboxes_px = _norm_bboxes_to_px(seed_boxes, w, h)
        stream_results = _run_video_predictor(clip_path, weight_path, bboxes_px)

        for i, result in enumerate(stream_results):
            if _abort.is_set():
                _set(
                    status="aborted",
                    message="Propagate прерван",
                    results=list(results),
                    processed=len(results),
                    mask_total=mask_total,
                    progress=len(results) / written if written else 0.0,
                )
                return
            frame_idx = start_frame + i
            t = float(frame_idx) / clip_fps
            masks = _results_to_frame_masks(result, h, w)
            results.append(
                {
                    "time_sec": round(t, 3),
                    "frame_idx": frame_idx,
                    "masks": masks,
                }
            )
            mask_total += len(masks)
            _set(
                processed=len(results),
                mask_total=mask_total,
                progress=min(1.0, len(results) / written if written else 1.0),
                results=list(results),
                message=f"Кадр {len(results)}/{written} · масок {mask_total}",
            )

        if persist and results:
            persisted = _persist_results(
                source_video=source_key, track_id=task_id, results=results
            )

        _set(
            status="done",
            progress=1.0,
            processed=len(results),
            mask_total=mask_total,
            persisted=persisted,
            results=list(results),
            message=(
                f"Готово: {len(results)} кадров, {mask_total} масок"
                + (f", SQLite {persisted}" if persist else "")
            ),
            error=None,
        )
    except Exception as exc:  # noqa: BLE001
        _set(
            status="error",
            error=str(exc),
            message=f"Ошибка propagate: {exc}",
            results=list(results),
            processed=len(results),
            mask_total=mask_total,
            persisted=persisted,
        )
    finally:
        if clip_path is not None:
            try:
                clip_path.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
        if clip_dir is not None:
            try:
                clip_dir.rmdir()
            except Exception:  # noqa: BLE001
                pass
        _empty_cache()


def start(
    *,
    video_path: str,
    time_sec: float,
    max_frames: int = MAX_PROPAGATE_FRAMES,
    points: list[dict[str, Any]] | None = None,
    bboxes: list[dict[str, Any]] | None = None,
    persist: bool = False,
) -> dict[str, Any]:
    global _thread
    points = points or []
    bboxes = bboxes or []
    if not points and not bboxes:
        raise ValueError("points or bboxes required")

    engine = get_sam3_engine()
    st = engine.status()
    if not st.get("ready"):
        raise FileNotFoundError("SAM3 weight missing")
    if not st.get("loaded"):
        raise RuntimeError("SAM3 model not loaded")

    video_abs, source_key = _resolve_video(video_path)
    frames = max(1, min(MAX_PROPAGATE_FRAMES, int(max_frames)))
    t = float(max(0.0, time_sec))

    with _lock:
        if _state["status"] == "running" or (_thread is not None and _thread.is_alive()):
            raise RuntimeError("SAM3 propagate уже выполняется")
        task_id = uuid.uuid4().hex[:12]
        _abort.clear()
        _state.update(
            {
                "task_id": task_id,
                "status": "running",
                "progress": 0.0,
                "processed": 0,
                "sample_total": frames,
                "mask_total": 0,
                "persisted": 0,
                "message": "Старт SAM3 propagate…",
                "error": None,
                "video_path": str(video_path),
                "max_frames": frames,
                "persist": bool(persist),
                "results": [],
            }
        )
        thr = threading.Thread(
            target=_run,
            args=(
                task_id,
                video_abs,
                source_key,
                t,
                frames,
                points,
                bboxes,
                bool(persist),
            ),
            name=f"sam3-prop-{task_id}",
            daemon=True,
        )
        _thread = thr
        thr.start()

    return _snapshot(include_results=False)


def abort(task_id: str) -> dict[str, Any]:
    with _lock:
        if _state["task_id"] != task_id:
            raise KeyError(f"unknown task_id: {task_id}")
        if _state["status"] != "running":
            return _snapshot(include_results=True)
    _abort.set()
    deadline = time.time() + 5.0
    while time.time() < deadline:
        with _lock:
            if _state["status"] != "running":
                break
        time.sleep(0.05)
    return status(task_id)
