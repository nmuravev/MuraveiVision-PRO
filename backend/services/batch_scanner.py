"""Background batch YOLO scan of archive videos → SQLite detections + SSE progress."""
from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
from services.db import insert_detection, normalize_media_path, save_crop_jpeg
from services.security import archive_root, assert_in_archive
from services.telemetry import attach_gps, ensure_track_for_video
from services.yolo_engine import get_yolo_engine

LOG_PATH = BASE_DIR / "logs" / "batch_scan.log"

_lock = threading.Lock()
_state: dict[str, Any] = {
    "status": "idle",  # idle|running|done|error
    "task_id": None,
    "message": "",
    "video_path": None,
    "source_video": None,
    "current_frame": 0,
    "total_frames": 0,
    "processed": 0,
    "sample_total": 0,
    "detections_found": 0,
    "time_sec": 0.0,
    "fps_sample": 1.0,
    "conf": 0.25,
    "started_at": None,
    "finished_at": None,
    "error": None,
}
_events: list[dict[str, Any]] = []
_stop = threading.Event()
_thread: threading.Thread | None = None


def _log(msg: str) -> None:
    from services import runtime_log

    runtime_log.info("scan", msg)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _emit(event: dict[str, Any]) -> None:
    payload = {"ts": time.time(), **event}
    with _lock:
        _events.append(payload)
        if len(_events) > 800:
            del _events[:400]
        for k, v in event.items():
            if k in _state:
                _state[k] = v
        if "status" in event:
            _state["status"] = event["status"]
        if "message" in event:
            _state["message"] = event["message"]
        if "error" in event:
            _state["error"] = event["error"]


def status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def drain_events(after_idx: int = 0) -> tuple[list[dict[str, Any]], int]:
    with _lock:
        chunk = _events[after_idx:]
        return chunk, len(_events)


def _canonical_source(path: Path) -> str:
    """Prefer archive-relative path with forward slashes for stable source_video keys."""
    try:
        rel = path.resolve().relative_to(archive_root().resolve())
        return normalize_media_path(rel.as_posix())
    except Exception:
        return normalize_media_path(str(path))


def _resolve_video(video_path: str) -> tuple[Path, str]:
    """Return (absolute file, source_video key for DB/timeline).

    Prefer the client-supplied path string when it already resolves under archive/
    so Timeline filters (`sourcePath === source_video`) keep working.
    """
    raw = (video_path or "").strip()
    if not raw:
        raise ValueError("video_path пуст")
    p = Path(raw)
    if not p.is_absolute():
        cand = (
            BASE_DIR / raw
            if raw.replace("\\", "/").startswith("archive/")
            else archive_root() / raw
        )
        p = cand
    target = assert_in_archive(p)
    if not target.is_file():
        raise FileNotFoundError(f"Видео не найдено: {target}")
    if target.suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        raise ValueError(f"Неподдерживаемый формат: {target.suffix}")
    # Always store normalized relative-to-archive key
    client_key = normalize_media_path(raw)
    source_key = client_key if client_key else _canonical_source(target)
    if not source_key:
        source_key = _canonical_source(target)
    return target, source_key


def _xywh_from_obj(obj: dict[str, Any]) -> tuple[float, float, float, float]:
    bbox = obj.get("bbox") or {}
    x1 = float(bbox.get("x1", 0))
    y1 = float(bbox.get("y1", 0))
    x2 = float(bbox.get("x2", 0))
    y2 = float(bbox.get("y2", 0))
    x = min(x1, x2)
    y = min(y1, y2)
    w = max(0.01, abs(x2 - x1))
    h = max(0.01, abs(y2 - y1))
    return x, y, w, h


def _run(
    task_id: str,
    video_abs: Path,
    source_video: str,
    fps_sample: float,
    conf: float,
    save_crops: bool,
) -> None:
    global _thread
    import cv2

    try:
        _emit(
            {
                "status": "running",
                "message": "Открытие видео…",
                "task_id": task_id,
                "video_path": str(video_abs),
                "source_video": source_video,
                "error": None,
            }
        )
        cap = cv2.VideoCapture(str(video_abs))
        if not cap.isOpened():
            raise RuntimeError(f"Не удалось открыть видео: {video_abs.name}")

        fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        if fps <= 0:
            fps = 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        sample = max(0.1, float(fps_sample))
        frame_step = max(1, int(round(fps / sample)))
        sample_total = max(1, (total + frame_step - 1) // frame_step) if total > 0 else 0
        _emit(
            {
                "message": f"Скан {video_abs.name}: fps={fps:.1f}, шаг={frame_step}, кадров≈{total}",
                "total_frames": max(total, 1),
                "sample_total": sample_total,
                "current_frame": 0,
                "processed": 0,
                "detections_found": 0,
            }
        )
        _log(
            f"start task={task_id} file={video_abs.name} fps={fps:.2f} "
            f"step={frame_step} total={total} conf={conf}"
        )

        track: list[dict[str, Any]] = []
        try:
            track = ensure_track_for_video(source_video)
            if track:
                _emit({"message": f"Телеметрия: {len(track)} точек GPS"})
                _log(f"telemetry points={len(track)} for {source_video}")
        except Exception as exc:  # noqa: BLE001
            _log(f"telemetry skip: {exc}")

        engine = get_yolo_engine()
        found = 0
        processed = 0
        frame_idx = 0
        viewer_id = f"batch-{task_id[:8]}"

        while True:
            if _stop.is_set():
                _emit({"status": "idle", "message": "Остановлено оператором"})
                cap.release()
                return

            if total > 0 and frame_idx >= total:
                break

            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                if total <= 0:
                    break
                frame_idx += frame_step
                continue

            time_sec = float(frame_idx) / fps
            ok_enc, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok_enc:
                frame_idx += frame_step
                continue
            jpeg = buf.tobytes()
            res = engine._predict_sync(jpeg, conf, frame_idx, time_sec, viewer_id=viewer_id)  # noqa: SLF001
            objects = res.get("objects") or []
            for obj in objects:
                x, y, w, h = _xywh_from_obj(obj)
                class_name = str(obj.get("class_en") or obj.get("class_name") or "unknown")
                class_id = int(obj.get("class_id") or 0)
                payload: dict[str, Any] = {
                    "source_video": source_video,
                    "time_sec": time_sec,
                    "frame_idx": frame_idx,
                    "class_id": class_id,
                    "class_name": class_name,
                    "ai_class_name": class_name,
                    "confidence": float(obj.get("confidence") or 0),
                    "bbox_x": x,
                    "bbox_y": y,
                    "bbox_w": w,
                    "bbox_h": h,
                    "origin": "batch_scan",
                }
                row = insert_detection(attach_gps(payload))
                if save_crops:
                    crop_path = save_crop_jpeg(
                        row["id"], jpeg, {"x": x, "y": y, "w": w, "h": h}
                    )
                    if crop_path:
                        from services.db import update_detection

                        update_detection(row["id"], {"crop_path": crop_path})
                found += 1

            processed += 1
            _emit(
                {
                    "status": "running",
                    "current_frame": frame_idx,
                    "total_frames": max(total, frame_idx + 1),
                    "processed": processed,
                    "detections_found": found,
                    "time_sec": time_sec,
                    "message": (
                        f"Обработано {processed} кадров"
                        + (f" из ~{max(1, total // frame_step)}" if total else "")
                        + f", найдено {found} целей"
                    ),
                }
            )
            frame_idx += frame_step

        cap.release()
        _emit(
            {
                "status": "done",
                "message": f"Готово: {found} детекций, {processed} кадров",
                "detections_found": found,
                "processed": processed,
                "finished_at": time.time(),
            }
        )
        _log(f"done task={task_id} found={found} processed={processed}")
    except Exception as exc:  # noqa: BLE001
        _log(f"ERROR {exc}")
        _emit(
            {
                "status": "error",
                "error": str(exc),
                "message": str(exc),
                "finished_at": time.time(),
            }
        )
    finally:
        with _lock:
            _thread = None


def start(
    video_path: str,
    fps_sample: float = 1.0,
    conf: float = 0.25,
    save_crops: bool = True,
) -> dict[str, Any]:
    global _thread
    with _lock:
        if _state["status"] == "running" or (_thread and _thread.is_alive()):
            raise RuntimeError("Скан уже выполняется")
        video_abs, source_video = _resolve_video(video_path)
        task_id = uuid.uuid4().hex[:12]
        _stop.clear()
        _events.clear()
        _state.update(
            {
                "status": "running",
                "task_id": task_id,
                "message": "Запуск…",
                "video_path": str(video_abs),
                "source_video": source_video,
                "current_frame": 0,
                "total_frames": 0,
                "processed": 0,
                "sample_total": 0,
                "detections_found": 0,
                "time_sec": 0.0,
                "fps_sample": float(fps_sample),
                "conf": float(conf),
                "started_at": time.time(),
                "finished_at": None,
                "error": None,
            }
        )
        _thread = threading.Thread(
            target=_run,
            args=(task_id, video_abs, source_video, float(fps_sample), float(conf), bool(save_crops)),
            daemon=True,
            name="batch-scan",
        )
        from services import runtime_log

        runtime_log.cmd(
            "scan",
            [
                "batch_yolo_scan",
                str(video_abs),
                f"--fps_sample={fps_sample}",
                f"--conf={conf}",
                f"--save_crops={save_crops}",
            ],
        )
        _thread.start()
    return status()


def stop() -> dict[str, Any]:
    _stop.set()
    _emit({"message": "Остановка запрошена…"})
    return status()
