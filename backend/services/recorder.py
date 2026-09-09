"""Session recorder: ffmpeg (preferred) or OpenCV VideoWriter → archive/recordings/{drone_id}/."""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from config import BASE_DIR

RECORD_ROOT = BASE_DIR / "archive" / "recordings"
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def _job_alive(job: dict[str, Any]) -> bool:
    proc: subprocess.Popen | None = job.get("proc")
    if proc is not None:
        return proc.poll() is None
    thread: threading.Thread | None = job.get("thread")
    return bool(thread and thread.is_alive())


def recordings_dir(drone_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (drone_id or "drone"))
    path = RECORD_ROOT / (safe or "drone")
    path.mkdir(parents=True, exist_ok=True)
    return path


def status(drone_id: str | None = None) -> dict[str, Any]:
    with _lock:
        if drone_id:
            job = _jobs.get(drone_id)
            if not job or not _job_alive(job):
                if job:
                    _jobs.pop(drone_id, None)
                return {"recording": False, "drone_id": drone_id}
            return {
                "recording": True,
                "drone_id": drone_id,
                "path": str(job["path"]),
                "started_at": job["started_at"],
                "backend": job["backend"],
            }
        dead = [key for key, job in _jobs.items() if not _job_alive(job)]
        for key in dead:
            _jobs.pop(key, None)
        return {
            "recording": bool(_jobs),
            "jobs": [
                {
                    "drone_id": key,
                    "path": str(job["path"]),
                    "started_at": job["started_at"],
                    "backend": job["backend"],
                }
                for key, job in _jobs.items()
            ],
        }


def _ffmpeg_bin() -> str | None:
    from services.ffmpeg_util import ffmpeg_bin

    return ffmpeg_bin()



def _start_ffmpeg(source: Path, dest: Path, start_sec: float) -> subprocess.Popen:
    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-re",
        "-ss",
        f"{max(0.0, start_sec):.3f}",
        "-i",
        str(source),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        str(dest),
    ]
    # DEVNULL: unread PIPE buffers deadlock ffmpeg after ~30s of logging.
    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )


def _opencv_loop(source: Path, dest: Path, start_sec: float, stop_event: threading.Event) -> None:
    import cv2

    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        print(f"[REC] OpenCV cannot open {source}")
        return
    if start_sec > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000.0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) or 1280
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0) or 720
    writer = cv2.VideoWriter(str(dest), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    delay = 1.0 / fps
    try:
        while not stop_event.is_set():
            t0 = time.time()
            ok, frame = cap.read()
            if not ok:
                break
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))
            writer.write(frame)
            sleep_for = delay - (time.time() - t0)
            if sleep_for > 0:
                time.sleep(sleep_for)
    finally:
        writer.release()
        cap.release()
        print(f"[REC] OpenCV stopped → {dest}")


def start(drone_id: str, source_path: str, start_sec: float = 0.0) -> dict[str, Any]:
    drone = drone_id or "viewer-1"
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(str(source))
    with _lock:
        if drone in _jobs:
            raise RuntimeError("already recording")
        dest = recordings_dir(drone) / time.strftime("rec_%Y%m%d_%H%M%S.mp4")
        job: dict[str, Any] = {
            "path": dest,
            "started_at": time.time(),
            "backend": "opencv",
            "proc": None,
            "stop": threading.Event(),
            "thread": None,
        }
        ffmpeg = _ffmpeg_bin()
        if ffmpeg:
            try:
                proc = _start_ffmpeg(source, dest, start_sec)
                job["proc"] = proc
                job["backend"] = "ffmpeg"
                _jobs[drone] = job
                print(f"[REC] ffmpeg pid={proc.pid} → {dest}")
                return {"ok": True, "path": str(dest), "drone_id": drone, "backend": "ffmpeg"}
            except Exception as exc:  # noqa: BLE001
                print(f"[REC] ffmpeg start failed ({exc}), OpenCV fallback")
        stop = job["stop"]
        thread = threading.Thread(
            target=_opencv_loop,
            args=(source, dest, start_sec, stop),
            daemon=True,
            name=f"rec-{drone}",
        )
        job["thread"] = thread
        _jobs[drone] = job
        thread.start()
        print(f"[REC] OpenCV → {dest}")
        return {"ok": True, "path": str(dest), "drone_id": drone, "backend": "opencv"}


def stop(drone_id: str) -> dict[str, Any]:
    drone = drone_id or "viewer-1"
    with _lock:
        job = _jobs.pop(drone, None)
    if not job:
        return {"ok": True, "recording": False, "drone_id": drone, "path": None}
    proc: subprocess.Popen | None = job.get("proc")
    if proc is not None:
        try:
            if proc.stdin:
                proc.stdin.write(b"q\n")
                proc.stdin.flush()
            proc.wait(timeout=8)
        except Exception:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
    stop_event: threading.Event | None = job.get("stop")
    if stop_event is not None:
        stop_event.set()
    thread = job.get("thread")
    if thread is not None:
        thread.join(timeout=8)
    path = Path(job["path"])
    size = path.stat().st_size if path.is_file() else 0
    print(f"[REC] stop {drone} size={size} {path}")
    return {
        "ok": True,
        "recording": False,
        "drone_id": drone,
        "path": str(path) if path.is_file() else None,
        "bytes": size,
    }
