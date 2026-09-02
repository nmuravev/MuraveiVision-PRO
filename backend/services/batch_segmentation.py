"""P3.13.2: archive-only batch segmentation (frame_step sampling).

Reuses segmentation_engine only. Does not write detections/train or touch
yolo_engine / change_detection. One global job at a time.
"""
from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Any

import cv2

from services.segmentation_engine import DEFAULT_CONF, get_seg_engine

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
    "message": "",
    "error": None,
    "video_path": None,
    "frame_step": 30,
    "confidence": DEFAULT_CONF,
    "results": [],
    "owned_load": False,
    "sam_unloaded": False,
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
            "message": _state["message"],
            "error": _state["error"],
            "video_path": _state["video_path"],
            "frame_step": int(_state["frame_step"]),
            "confidence": float(_state["confidence"]),
            "sam_unloaded": bool(_state.get("sam_unloaded")),
        }
        if include_results or _state["status"] in ("done", "aborted", "error"):
            out["results"] = list(_state["results"])
        else:
            out["results"] = None
        return out


def status(task_id: str | None = None) -> dict[str, Any]:
    with _lock:
        current = _state["task_id"]
    if task_id is not None and current is not None and task_id != current:
        raise KeyError(f"unknown task_id: {task_id}")
    if task_id is not None and current is None:
        raise KeyError(f"unknown task_id: {task_id}")
    terminal = False
    with _lock:
        terminal = _state["status"] in ("done", "aborted", "error")
    return _snapshot(include_results=terminal)


def _set(**kwargs: Any) -> None:
    with _lock:
        for k, v in kwargs.items():
            if k in _state:
                _state[k] = v


def _resolve_video(video_path: str) -> tuple[Path, str]:
    from services.batch_scanner import _resolve_video as resolve

    return resolve(video_path)


def _run(
    task_id: str,
    video_abs: Path,
    frame_step: int,
    confidence: float,
    weight: str | None,
) -> None:
    engine = get_seg_engine()
    owned_load = False
    cap: cv2.VideoCapture | None = None
    results: list[dict[str, Any]] = []
    mask_total = 0
    processed = 0

    try:
        st = engine.status()
        if not st.get("loaded"):
            engine.load_model(weight)
            owned_load = True
            _set(owned_load=True)

        cap = cv2.VideoCapture(str(video_abs))
        if not cap.isOpened():
            raise RuntimeError(f"Не удалось открыть видео: {video_abs.name}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        if fps <= 0:
            fps = 25.0
        step = max(1, int(frame_step))
        sample_total = max(1, (total_frames + step - 1) // step) if total_frames > 0 else 0
        _set(
            sample_total=sample_total,
            message=f"Batch seg {video_abs.name}: fps={fps:.1f}, шаг={step}, кадров≈{total_frames}",
            progress=0.0,
        )

        frame_idx = 0
        while True:
            if _abort.is_set():
                _set(
                    status="aborted",
                    message="Batch сегментация прервана",
                    results=list(results),
                    processed=processed,
                    mask_total=mask_total,
                    progress=processed / sample_total if sample_total else 0.0,
                )
                return

            if total_frames > 0 and frame_idx >= total_frames:
                break

            cap.set(cv2.CAP_PROP_POS_FRAMES, float(frame_idx))
            ok, frame = cap.read()
            if not ok or frame is None:
                if total_frames <= 0:
                    break
                frame_idx += step
                continue

            ok_jpg, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok_jpg:
                frame_idx += step
                continue

            out = engine.infer_jpeg(buf.tobytes(), confidence)
            masks = list(out.get("masks") or [])
            time_sec = float(frame_idx) / fps
            results.append({"time_sec": round(time_sec, 3), "masks": masks})
            mask_total += len(masks)
            processed += 1
            progress = processed / sample_total if sample_total else 0.0
            _set(
                processed=processed,
                mask_total=mask_total,
                progress=min(1.0, progress),
                results=list(results),
                message=f"Кадр {processed}/{sample_total or '?'} · масок {mask_total}",
            )
            frame_idx += step

            # Guard when FRAME_COUNT unknown: stop after empty reads streak
            if total_frames <= 0 and processed >= 10_000:
                break

        _set(
            status="done",
            progress=1.0,
            processed=processed,
            mask_total=mask_total,
            results=list(results),
            message=f"Готово: {processed} кадров, {mask_total} масок",
            error=None,
        )
    except Exception as exc:  # noqa: BLE001
        _set(
            status="error",
            error=str(exc),
            message=f"Ошибка batch seg: {exc}",
            results=list(results),
            processed=processed,
            mask_total=mask_total,
        )
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:  # noqa: BLE001
                pass
        if owned_load:
            try:
                engine.unload_model()
            except Exception:  # noqa: BLE001
                pass
            _set(owned_load=False)


def start(
    *,
    video_path: str,
    frame_step: int = 30,
    confidence: float = DEFAULT_CONF,
    weight: str | None = None,
) -> dict[str, Any]:
    global _thread
    video_abs, _source = _resolve_video(video_path)
    step = max(1, min(300, int(frame_step)))
    conf = float(max(0.05, min(0.99, confidence)))

    sam_unloaded = False
    try:
        from services.sam3_engine import get_sam3_engine

        eng = get_sam3_engine()
        if eng.status().get("loaded"):
            eng.unload_model()
            sam_unloaded = True
    except Exception:  # noqa: BLE001
        pass

    with _lock:
        if _state["status"] == "running" or (_thread is not None and _thread.is_alive()):
            raise RuntimeError("Batch сегментация уже выполняется")
        task_id = uuid.uuid4().hex[:12]
        _abort.clear()
        _state.update(
            {
                "task_id": task_id,
                "status": "running",
                "progress": 0.0,
                "processed": 0,
                "sample_total": 0,
                "mask_total": 0,
                "message": "Старт batch сегментации…",
                "error": None,
                "video_path": str(video_path),
                "frame_step": step,
                "confidence": conf,
                "results": [],
                "owned_load": False,
                "sam_unloaded": sam_unloaded,
            }
        )
        thr = threading.Thread(
            target=_run,
            args=(task_id, video_abs, step, conf, weight),
            name=f"batch-seg-{task_id}",
            daemon=True,
        )
        _thread = thr
        thr.start()

    out = _snapshot(include_results=False)
    out["sam_unloaded"] = sam_unloaded
    return out


def abort(task_id: str) -> dict[str, Any]:
    with _lock:
        if _state["task_id"] != task_id:
            raise KeyError(f"unknown task_id: {task_id}")
        if _state["status"] != "running":
            return _snapshot(include_results=True)
    _abort.set()
    # Wait briefly for worker to mark aborted
    deadline = time.time() + 5.0
    while time.time() < deadline:
        with _lock:
            if _state["status"] != "running":
                break
        time.sleep(0.05)
    return status(task_id)
