"""Locate the 9-minute field DJI clip and shared extracted frames (zero hardcode).

Resolution order:
1. Env ``MURAVEI_TEST_LONG_CLIP`` (repo-relative or absolute)
2. ``archive/video_2026-08-25_09-17-15.mp4`` under repo root
3. Same name under ``MuraveiVision-Pro-3.2.0/archive/`` (isolated copy)

Frame cache: ``archive/.test_cache/long_clip_frames/`` (gitignored).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from services.security import BASE_DIR

_CLIP_BASENAME = "video_2026-08-25_09-17-15.mp4"
_CACHE_REL = Path("archive") / ".test_cache" / "long_clip_frames"


def resolve_long_clip() -> Path | None:
    env = (os.environ.get("MURAVEI_TEST_LONG_CLIP") or "").strip()
    candidates: list[Path] = []
    if env:
        p = Path(env)
        candidates.append(p if p.is_absolute() else (BASE_DIR / p))
    candidates.append(BASE_DIR / "archive" / _CLIP_BASENAME)
    candidates.append(BASE_DIR / "MuraveiVision-Pro-3.2.0" / "archive" / _CLIP_BASENAME)
    for c in candidates:
        try:
            if c.is_file() and c.stat().st_size > 1_000_000:
                return c.resolve()
        except OSError:
            continue
    return None


def long_clip_skip_reason() -> str:
    return (
        "9-min field clip missing — set MURAVEI_TEST_LONG_CLIP or place "
        f"archive/{_CLIP_BASENAME}"
    )


def shared_frames_dir() -> Path:
    d = BASE_DIR / _CACHE_REL
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_shared_frames(
    clip: Path,
    *,
    t_start: float = 0.0,
    t_end: float = 60.0,
    fps: float = 1.0,
    max_side: int = 960,
) -> tuple[Path, int]:
    """Extract once into cache; reuse if enough JPGs already present.

    Returns (frames_dir, count).
    """
    out = shared_frames_dir() / f"seg_{int(t_start)}_{int(t_end)}_fps{fps:g}"
    marker = out / ".ok"
    existing = sorted(out.glob("*.jpg")) if out.is_dir() else []
    if marker.is_file() and len(existing) >= 10:
        return out, len(existing)

    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)

    # Prefer project ffmpeg if present
    ffmpeg = BASE_DIR / "assets" / "ffmpeg" / "ffmpeg.exe"
    if not ffmpeg.is_file():
        ffmpeg = BASE_DIR / "assets" / "ffmpeg.exe"
    ff = str(ffmpeg) if ffmpeg.is_file() else "ffmpeg"

    # scale for HUD tests; COLMAP tests may re-extract at full pipeline size
    vf = f"fps={fps},scale='min({max_side},iw)':-2"
    pattern = str(out / "%06d.jpg")
    cmd = [
        ff,
        "-y",
        "-ss",
        str(t_start),
        "-i",
        str(clip),
        "-t",
        str(max(0.1, t_end - t_start)),
        "-vf",
        vf,
        "-q:v",
        "3",
        pattern,
    ]
    subprocess.run(cmd, capture_output=True, check=False, timeout=600)
    jpgs = sorted(out.glob("*.jpg"))
    if len(jpgs) < 3:
        raise RuntimeError(f"ffmpeg extracted {len(jpgs)} frames from {clip.name}")
    marker.write_text(str(len(jpgs)), encoding="utf-8")
    return out, len(jpgs)
