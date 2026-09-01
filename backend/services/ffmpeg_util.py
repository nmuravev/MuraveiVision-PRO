"""ffmpeg/ffprobe helpers (archive media duration, cuts)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

BASE_DIR = Path(__file__).resolve().parents[2]


def ffmpeg_bin() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    for cand in (
        BASE_DIR / "assets" / "ffmpeg.exe",
        BASE_DIR / "assets" / "ffmpeg" / "ffmpeg.exe",
        BASE_DIR / "assets" / "ffmpeg",
    ):
        if cand.is_file():
            return str(cand)
    return None


def ffprobe_bin() -> str | None:
    found = shutil.which("ffprobe")
    if found:
        return found
    for cand in (
        BASE_DIR / "assets" / "ffprobe.exe",
        BASE_DIR / "assets" / "ffmpeg" / "ffprobe.exe",
        BASE_DIR / "assets" / "ffmpeg" / "ffprobe",
    ):
        if cand.is_file():
            return str(cand)
    return None


def video_duration_ffprobe(path: Path, timeout: float = 12.0) -> float | None:
    probe = ffprobe_bin()
    if not probe:
        return None
    cmd = [
        probe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        from services import runtime_log

        runtime_log.cmd("ffmpeg", cmd)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            if err:
                runtime_log.write("warn", "ffmpeg", err[:400], kind="stderr")
            return None
        data = json.loads(proc.stdout or "{}")
        raw = (data.get("format") or {}).get("duration")
        if raw is None:
            return None
        val = float(raw)
        if val <= 0:
            return None
        return round(val, 2)
    except (subprocess.TimeoutExpired, ValueError, json.JSONDecodeError, OSError):
        return None


def video_duration_opencv(path: Path) -> float | None:
    try:
        import cv2

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return None
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0) or 25.0
        nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        if nframes <= 0:
            return None
        return round(nframes / fps, 2)
    except Exception:  # noqa: BLE001
        return None


def is_video_readable(path: Path, timeout: float = 12.0) -> bool:
    """True when container has valid moov/duration (ffprobe)."""
    return video_duration_ffprobe(path, timeout=timeout) is not None


def video_duration_sec(path: Path) -> float | None:
    """ffprobe first (moov-at-end MP4); OpenCV fallback."""
    dur = video_duration_ffprobe(path)
    if dur is not None:
        return dur
    return video_duration_opencv(path)
