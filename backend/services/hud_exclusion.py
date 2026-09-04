"""Automatic HUD/OSD border exclusion for drone footage (classical CV, air-gap safe).

Relative margins only (0–1). Mask for detect/CD (blur/feather); crop for recon.
Cache keyed by archive-relative video + size/mtime fingerprint. Non-blocking.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from services.runtime_log import write as runtime_write
from services.security import BASE_DIR, resolve_under_archive

ANALYSIS_ROOT = BASE_DIR / "archive" / "analysis"
PROFILES_PATH = BASE_DIR / "config" / "hud_profiles.json"

# Relative band search limits (fractions of H/W) — not absolute pixels
_MAX_BAND = 0.35
_MIN_BAND = 0.04
_SAMPLE_COUNT = 10
_MOTION_EPS = 4.0  # mean absdiff gray; below → static camera → no-op
_STATIC_RATIO = 0.55  # band vs interior static score threshold
_FEATHER = 0.015  # relative feather width for blur blend

_lock = threading.Lock()
_mem: dict[str, "HudZones"] = {}
_inflight: set[str] = set()


@dataclass
class HudZones:
    top: float = 0.0
    bottom: float = 0.0
    left: float = 0.0
    right: float = 0.0
    source: str = "auto"  # auto | manual | profile | none
    ready: bool = True
    version: int = 1
    fingerprint: dict[str, int] | None = None
    updated_at: float = 0.0
    video_key: str = ""

    def has_exclusion(self) -> bool:
        return self.ready and (self.top > 0 or self.bottom > 0 or self.left > 0 or self.right > 0)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def empty_zones(*, ready: bool = True, source: str = "none") -> HudZones:
    return HudZones(ready=ready, source=source, updated_at=time.time())


def video_fingerprint(video: Path) -> dict[str, int]:
    st = video.stat()
    mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
    return {"size": int(st.st_size), "mtime_ns": int(mtime_ns)}


def archive_rel_key(source_video: str) -> str:
    """Stable cache key from archive-relative path (no host paths)."""
    raw = str(source_video or "").replace("\\", "/").lstrip("/")
    if raw.lower().startswith("archive/"):
        raw = raw[len("archive/") :]
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    slug = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(raw).name)[:48]
    return f"{slug}_{digest}"


def cache_path(video_key: str) -> Path:
    return ANALYSIS_ROOT / video_key / "hud_zones.json"


def _load_profiles() -> dict[str, dict[str, float]]:
    if not PROFILES_PATH.is_file():
        return {}
    try:
        raw = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        runtime_write("warn", "hud", f"Invalid hud_profiles.json: {exc} — using auto")
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, float]] = {}
    for name, val in raw.items():
        if not isinstance(val, dict):
            continue
        try:
            entry = {
                "top": float(val.get("top") or 0),
                "bottom": float(val.get("bottom") or 0),
                "left": float(val.get("left") or 0),
                "right": float(val.get("right") or 0),
            }
        except (TypeError, ValueError):
            continue
        if any(v < 0 or v > _MAX_BAND for v in entry.values()):
            continue
        if sum(entry.values()) <= 0:
            continue
        out[str(name)] = entry
    return out


def _resolve_video(source_video: str) -> Path:
    return resolve_under_archive(source_video)


def _write_cache(zones: HudZones) -> None:
    path = cache_path(zones.video_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(zones.to_dict(), indent=2), encoding="utf-8")


def _read_cache(video_key: str) -> HudZones | None:
    path = cache_path(video_key)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return HudZones(
            top=float(raw.get("top") or 0),
            bottom=float(raw.get("bottom") or 0),
            left=float(raw.get("left") or 0),
            right=float(raw.get("right") or 0),
            source=str(raw.get("source") or "auto"),
            ready=bool(raw.get("ready", True)),
            version=int(raw.get("version") or 1),
            fingerprint=raw.get("fingerprint") if isinstance(raw.get("fingerprint"), dict) else None,
            updated_at=float(raw.get("updated_at") or 0),
            video_key=video_key,
        )
    except (TypeError, ValueError):
        return None


def _sample_frames(video: Path, n: int = _SAMPLE_COUNT) -> list[np.ndarray]:
    import cv2

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return []
    try:
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0) or 25.0
        duration = frame_count / fps if frame_count > 0 else 0.0
        if duration <= 0:
            # fallback: grab first few
            frames: list[np.ndarray] = []
            for _ in range(min(n, 5)):
                ok, fr = cap.read()
                if not ok or fr is None:
                    break
                frames.append(fr)
            return frames
        times = [duration * (i + 0.5) / n for i in range(n)]
        frames = []
        for t in times:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, fr = cap.read()
            if ok and fr is not None:
                frames.append(fr)
        return frames
    finally:
        cap.release()


def _gray_small(frame: np.ndarray, max_side: int = 320) -> np.ndarray:
    import cv2

    h, w = frame.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        frame = cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))))
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def detect_zones_from_frames(frames: list[np.ndarray]) -> HudZones:
    """Classical CV: motion gate + static border bands. Pure / testable."""
    if len(frames) < 3:
        return empty_zones(source="none")

    grays = [_gray_small(f) for f in frames]
    diffs = []
    for a, b in zip(grays[:-1], grays[1:]):
        if a.shape != b.shape:
            continue
        diffs.append(float(np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32)))))
    motion = float(np.mean(diffs)) if diffs else 0.0
    if motion < _MOTION_EPS:
        return empty_zones(source="none")

    # Temporal std per pixel across samples
    stack = np.stack([g.astype(np.float32) for g in grays if g.shape == grays[0].shape], axis=0)
    if stack.shape[0] < 3:
        return empty_zones(source="none")
    tstd = np.std(stack, axis=0)
    h, w = tstd.shape
    # Interior reference (central 50%)
    iy0, iy1 = int(h * 0.25), int(h * 0.75)
    ix0, ix1 = int(w * 0.25), int(w * 0.75)
    interior = float(np.mean(tstd[iy0:iy1, ix0:ix1])) + 1e-6

    def band_static(region: np.ndarray) -> float:
        # Low temporal variance + high edge density vs interior → HUD-like
        mean_std = float(np.mean(region))
        return float(interior / (mean_std + 1e-6))

    def best_margin(axis: str) -> float:
        best = 0.0
        steps = 12
        for i in range(1, steps + 1):
            frac = _MIN_BAND + (_MAX_BAND - _MIN_BAND) * (i / steps)
            if axis == "top":
                region = tstd[: max(1, int(h * frac)), :]
            elif axis == "bottom":
                region = tstd[h - max(1, int(h * frac)) :, :]
            elif axis == "left":
                region = tstd[:, : max(1, int(w * frac))]
            else:
                region = tstd[:, w - max(1, int(w * frac)) :]
            score = band_static(region)
            if score >= _STATIC_RATIO and frac > best:
                # Prefer largest band that still scores as static
                best = frac
            elif score < _STATIC_RATIO * 0.85 and best > 0:
                break
        return round(best, 4)

    # Also require edge density in candidate bands (HUD text/icons)
    import cv2

    edges = [cv2.Canny(g, 60, 150) for g in grays]
    edge_mean = np.mean(np.stack(edges, axis=0).astype(np.float32), axis=0)

    def edge_ok(axis: str, frac: float) -> bool:
        if frac <= 0:
            return False
        if axis == "top":
            region = edge_mean[: max(1, int(h * frac)), :]
        elif axis == "bottom":
            region = edge_mean[h - max(1, int(h * frac)) :, :]
        elif axis == "left":
            region = edge_mean[:, : max(1, int(w * frac))]
        else:
            region = edge_mean[:, w - max(1, int(w * frac)) :]
        return float(np.mean(region)) > 8.0

    top = best_margin("top")
    bottom = best_margin("bottom")
    left = best_margin("left")
    right = best_margin("right")
    if top and not edge_ok("top", top):
        top = 0.0
    if bottom and not edge_ok("bottom", bottom):
        bottom = 0.0
    if left and not edge_ok("left", left):
        left = 0.0
    if right and not edge_ok("right", right):
        right = 0.0

    # Safety: don't claim >60% of frame
    if top + bottom > 0.6:
        top = min(top, 0.3)
        bottom = min(bottom, 0.3)
    if left + right > 0.5:
        left = min(left, 0.2)
        right = min(right, 0.2)

    src = "auto" if (top or bottom or left or right) else "none"
    return HudZones(
        top=top,
        bottom=bottom,
        left=left,
        right=right,
        source=src,
        ready=True,
        updated_at=time.time(),
    )


def _compute_for_video(video: Path, video_key: str, fp: dict[str, int]) -> HudZones:
    t0 = time.time()
    frames = _sample_frames(video)
    zones = detect_zones_from_frames(frames)
    zones.video_key = video_key
    zones.fingerprint = fp
    zones.ready = True
    zones.updated_at = time.time()
    _write_cache(zones)
    elapsed = time.time() - t0
    runtime_write(
        "info",
        "hud",
        f"detect key={video_key} source={zones.source} "
        f"t={zones.top} b={zones.bottom} l={zones.left} r={zones.right} {elapsed:.2f}s",
    )
    return zones


def _bg_compute(source_video: str, video_key: str, video: Path, fp: dict[str, int]) -> None:
    try:
        zones = _compute_for_video(video, video_key, fp)
        with _lock:
            _mem[video_key] = zones
            _inflight.discard(video_key)
    except Exception as exc:  # noqa: BLE001
        runtime_write("error", "hud", f"bg compute failed: {exc}")
        z = empty_zones(ready=True, source="none")
        z.video_key = video_key
        z.fingerprint = fp
        _write_cache(z)
        with _lock:
            _mem[video_key] = z
            _inflight.discard(video_key)


def _fp_equal(a: dict[str, int] | None, b: dict[str, int] | None) -> bool:
    if not a or not b:
        return False
    try:
        return int(a.get("size", -1)) == int(b.get("size", -2)) and int(
            a.get("mtime_ns", -1)
        ) == int(b.get("mtime_ns", -2))
    except (TypeError, ValueError):
        return False


def get_zones(
    source_video: str,
    *,
    force: bool = False,
    wait: bool = False,
    kickoff: bool = True,
) -> HudZones:
    """Return cached/ready zones; never blocks long unless wait=True.

    kickoff=True starts background compute on miss. Pipelines should use wait=False.
    """
    try:
        video = _resolve_video(source_video)
    except Exception:  # noqa: BLE001 — path errors → no-op
        return empty_zones(source="none")
    if not video.is_file():
        return empty_zones(source="none")

    video_key = archive_rel_key(source_video)
    fp = video_fingerprint(video)

    with _lock:
        mem = _mem.get(video_key)
        if mem and not force and _fp_equal(mem.fingerprint, fp) and mem.ready:
            return mem
        cached = None if force else _read_cache(video_key)
        if (
            cached
            and _fp_equal(cached.fingerprint, fp)
            and cached.ready
            and cached.source != "pending"
        ):
            _mem[video_key] = cached
            return cached
        if video_key in _inflight and not wait:
            pending = empty_zones(ready=False, source="pending")
            pending.video_key = video_key
            pending.fingerprint = fp
            return pending

    if not kickoff and not wait:
        return empty_zones(ready=False, source="pending")

    if wait:
        zones = _compute_for_video(video, video_key, fp)
        with _lock:
            _mem[video_key] = zones
            _inflight.discard(video_key)
        return zones

    # Non-blocking: mark pending + background
    pending = empty_zones(ready=False, source="pending")
    pending.video_key = video_key
    pending.fingerprint = fp
    with _lock:
        if video_key in _inflight:
            return pending
        _inflight.add(video_key)
        _mem[video_key] = pending
    th = threading.Thread(
        target=_bg_compute,
        args=(source_video, video_key, video, fp),
        name=f"hud-{video_key[:8]}",
        daemon=True,
    )
    th.start()
    return pending


def ensure_zones_async(source_video: str) -> HudZones:
    """Kickoff compute if needed; return current (possibly not ready)."""
    return get_zones(source_video, force=False, wait=False, kickoff=True)


def save_manual_zones(
    source_video: str,
    *,
    top: float,
    bottom: float,
    left: float,
    right: float,
) -> HudZones:
    video = _resolve_video(source_video)
    video_key = archive_rel_key(source_video)
    fp = video_fingerprint(video) if video.is_file() else {"size": 0, "mtime_ns": 0}

    def clamp(v: float) -> float:
        return round(max(0.0, min(_MAX_BAND, float(v))), 4)

    zones = HudZones(
        top=clamp(top),
        bottom=clamp(bottom),
        left=clamp(left),
        right=clamp(right),
        source="manual",
        ready=True,
        fingerprint=fp,
        updated_at=time.time(),
        video_key=video_key,
    )
    _write_cache(zones)
    with _lock:
        _mem[video_key] = zones
    return zones


def apply_blur_mask(frame: np.ndarray, zones: HudZones | None) -> np.ndarray:
    """Blur/feather HUD bands; keeps HxW. No-op if no zones. Never flat black."""
    if frame is None or zones is None or not zones.has_exclusion():
        return frame
    import cv2

    h, w = frame.shape[:2]
    top = int(round(zones.top * h))
    bottom = int(round(zones.bottom * h))
    left = int(round(zones.left * w))
    right = int(round(zones.right * w))
    if top + bottom >= h or left + right >= w:
        return frame

    k = max(31, (min(h, w) // 20) | 1)
    blurred = cv2.GaussianBlur(frame, (k, k), 0)
    # Soft alpha matte: 1 = replace with blur, 0 = keep original
    alpha = np.zeros((h, w), dtype=np.float32)
    if top > 0:
        alpha[:top, :] = 1.0
    if bottom > 0:
        alpha[h - bottom :, :] = 1.0
    if left > 0:
        alpha[:, :left] = np.maximum(alpha[:, :left], 1.0)
    if right > 0:
        alpha[:, w - right :] = np.maximum(alpha[:, w - right :], 1.0)

    feather = max(1, int(round(_FEATHER * min(h, w))))
    if feather > 1:
        alpha = cv2.GaussianBlur(alpha, (feather * 2 + 1, feather * 2 + 1), 0)
        alpha = np.clip(alpha, 0.0, 1.0)

    a3 = alpha[:, :, None]
    mixed = frame.astype(np.float32) * (1.0 - a3) + blurred.astype(np.float32) * a3
    return np.clip(mixed, 0, 255).astype(np.uint8)


def mask_jpeg_bytes(jpeg: bytes, zones: HudZones | None) -> bytes:
    """Decode → blur-mask → re-encode JPEG. Returns original on failure/no-op."""
    if not jpeg or zones is None or not zones.has_exclusion():
        return jpeg
    import cv2

    arr = np.frombuffer(jpeg, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        return jpeg
    masked = apply_blur_mask(frame, zones)
    ok, buf = cv2.imencode(".jpg", masked, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return buf.tobytes() if ok else jpeg


def crop_frame(frame: np.ndarray, zones: HudZones | None) -> tuple[np.ndarray, dict[str, float]]:
    """Crop clean interior for COLMAP. Returns (cropped, pixel_offsets relative 0-1)."""
    if frame is None or zones is None or not zones.has_exclusion():
        return frame, {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
    h, w = frame.shape[:2]
    top = int(round(zones.top * h))
    bottom = int(round(zones.bottom * h))
    left = int(round(zones.left * w))
    right = int(round(zones.right * w))
    y0, y1 = top, h - bottom
    x0, x1 = left, w - right
    if y1 - y0 < 32 or x1 - x0 < 32:
        return frame, {"top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}
    crop = frame[y0:y1, x0:x1]
    return crop, {
        "top": zones.top,
        "bottom": zones.bottom,
        "left": zones.left,
        "right": zones.right,
    }


def map_intrinsics_to_full_frame(
    intrinsics: dict[str, float],
    image_size: dict[str, int],
    hud_crop: dict[str, float] | None,
    full_width: int,
    full_height: int,
) -> tuple[dict[str, float], dict[str, int]]:
    """Shift COLMAP crop intrinsics into full-frame pixel space for raycast."""
    if not hud_crop or not any(float(hud_crop.get(k) or 0) for k in ("top", "bottom", "left", "right")):
        return intrinsics, image_size
    left = float(hud_crop.get("left") or 0) * full_width
    top = float(hud_crop.get("top") or 0) * full_height
    fx = float(intrinsics.get("fx") or 0)
    fy = float(intrinsics.get("fy") or 0)
    cx = float(intrinsics.get("cx") or 0) + left
    cy = float(intrinsics.get("cy") or 0) + top
    return (
        {"fx": fx, "fy": fy, "cx": cx, "cy": cy},
        {"width": int(full_width), "height": int(full_height)},
    )


def archive_hud_enabled() -> bool:
    from services.db import get_setting

    return (get_setting("hud_exclude_archive") or "1") == "1"


def live_hud_enabled() -> bool:
    from services.db import get_setting

    return (get_setting("hud_exclude_live") or "0") == "1"


def clear_mem_for_tests() -> None:
    with _lock:
        _mem.clear()
        _inflight.clear()
