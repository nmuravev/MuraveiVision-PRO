"""ffmpeg/ffprobe helpers (archive media duration, cuts)."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

BASE_DIR = Path(__file__).resolve().parents[2]
_LOG = logging.getLogger("muravei.ffmpeg")

SourceKind = Literal["env", "pack", "sidecar", "path", "missing"]


def _env_ffmpeg_dir() -> Path | None:
    raw = (os.environ.get("MURAVEI_FFMPEG_DIR") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_dir() else None


def _candidate_dirs() -> list[tuple[SourceKind, Path]]:
    out: list[tuple[SourceKind, Path]] = []
    env_dir = _env_ffmpeg_dir()
    if env_dir is not None:
        out.append(("env", env_dir))
    out.append(("pack", BASE_DIR / "assets" / "ffmpeg"))
    out.append(("sidecar", BASE_DIR / "sidecars" / "ffmpeg"))
    # Legacy flat layout under assets/
    out.append(("pack", BASE_DIR / "assets"))
    return out


def _find_named(exe: str) -> tuple[str | None, SourceKind]:
    names = (f"{exe}.exe", exe) if os.name == "nt" else (exe, f"{exe}.exe")
    for kind, root in _candidate_dirs():
        for name in names:
            cand = root / name
            if cand.is_file():
                return str(cand.resolve()), kind
    which = shutil.which(exe)
    if which:
        return which, "path"
    return None, "missing"


def resolve_ffmpeg() -> tuple[str | None, SourceKind]:
    """Order: MURAVEI_FFMPEG_DIR → assets/ffmpeg → sidecars/ffmpeg → PATH."""
    return _find_named("ffmpeg")


def resolve_ffprobe() -> tuple[str | None, SourceKind]:
    """Order: MURAVEI_FFMPEG_DIR → assets/ffmpeg → sidecars/ffmpeg → PATH."""
    return _find_named("ffprobe")


def ffmpeg_bin() -> str | None:
    path, source = resolve_ffmpeg()
    if path and source == "path":
        _LOG.warning("[ffmpeg] path=%s source=PATH (pack-local missing — degrade)", path)
        print(f"[ffmpeg] path={path} source=PATH")
    elif path:
        _LOG.info("[ffmpeg] path=%s source=%s", path, source)
        print(f"[ffmpeg] path={path} source={source}")
    return path


def ffprobe_bin() -> str | None:
    path, source = resolve_ffprobe()
    if path and source == "path":
        _LOG.warning("[ffprobe] path=%s source=PATH (pack-local missing — degrade)", path)
        print(f"[ffprobe] path={path} source=PATH")
    elif path:
        _LOG.info("[ffprobe] path=%s source=%s", path, source)
        print(f"[ffprobe] path={path} source={source}")
    return path


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