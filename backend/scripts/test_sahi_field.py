"""SAHI field test on a real 4K drone frame.

Extracts a raw frame from the drone video (preferred) or falls back to the
largest recon frame, then compares fast (no slicing) vs SAHI-sliced inference
at two slice sizes. Writes logs/sahi_field_test.json and prints a verdict.

This is an OBSERVATIONAL field test: it does NOT assert that SAHI finds more.
Exit 0 if both inference paths ran without error; exit 1 otherwise.

Run:
    muravei_env\\Scripts\\python.exe backend\\scripts\\test_sahi_field.py
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

# Classes we care about for the "small object" verdict.
SMALL_CLASSES = ("soldier", "truck", "person", "human", "pedestrian", "vehicle", "car")

DRONE_VIDEO_CANDIDATES = (
    "archive/video_2026-08-25_09-17-15.mp4",
    "archive/video_2026-08-25_09-17-15.mov",
)


def _extract_video_frame(video_path: Path) -> tuple[bytes, int, int] | None:
    """Extract a frame at ~50% timestamp from a video. Returns (jpg_bytes, w, h) or None."""
    try:
        import cv2  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        print(f"[sahi_field] cv2 unavailable: {exc}")
        return None
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"[sahi_field] could not open video: {video_path}")
        return None
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        mid = max(1, total // 2) if total > 0 else 1
        cap.set(cv2.CAP_PROP_POS_FRAMES, mid)
        ok, frame = cap.read()
        if not ok or frame is None:
            # retry from start
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        if not ok or frame is None:
            print(f"[sahi_field] could not read frame from: {video_path}")
            return None
        h, w = frame.shape[:2]
        ok2, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if not ok2:
            return None
        return buf.tobytes(), w, h
    finally:
        cap.release()


def _largest_recon_frame() -> tuple[bytes, Path] | None:
    """Fallback: largest jpg under archive/recon/*/frames/."""
    archive = ROOT / "archive"
    if not archive.is_dir():
        return None
    candidates: list[Path] = []
    for pat in ("*.jpg", "*.jpeg", "*.png"):
        candidates.extend(archive.rglob(pat))
    if not candidates:
        return None
    biggest = max(candidates, key=lambda p: p.stat().st_size if p.exists() else 0)
    try:
        return biggest.read_bytes(), biggest
    except Exception:  # noqa: BLE001
        return None


def _select_frame() -> tuple[bytes, str, int, int]:
    """Return (jpg_bytes, source_desc, w, h). Prefer raw drone video frame."""
    for rel in DRONE_VIDEO_CANDIDATES:
        vp = ROOT / rel
        if vp.exists():
            res = _extract_video_frame(vp)
            if res is not None:
                raw, w, h = res
                # Persist the extracted frame for reproducibility.
                logs_dir = ROOT / "logs"
                logs_dir.mkdir(parents=True, exist_ok=True)
                (logs_dir / "sahi_field_frame.jpg").write_bytes(raw)
                return raw, f"video:{rel}", w, h
    # Fallback to recon frame
    rc = _largest_recon_frame()
    if rc is not None:
        raw, path = rc
        try:
            from PIL import Image  # noqa: PLC0415

            with Image.open(io.BytesIO(raw)) as im:
                w, h = im.size
        except Exception:  # noqa: BLE001
            w, h = 0, 0
        return raw, f"recon:{path.relative_to(ROOT)}", w, h
    raise RuntimeError("No drone video and no archive frames found under archive/")


def _per_class_counts(objects: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for o in objects:
        name = str(o.get("class_en") or o.get("class_ru") or o.get("class_id", "?"))
        counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _small_count(objects: list[dict]) -> int:
    n = 0
    for o in objects:
        name = str(o.get("class_en") or o.get("class_ru") or "").lower()
        if any(s in name for s in SMALL_CLASSES):
            n += 1
    return n


async def main() -> int:
    import main  # noqa: F401  (initializes BASE_DIR / settings)
    from services.yolo_engine import get_yolo_engine

    raw, source, w, h = _select_frame()
    print(f"[sahi_field] frame source={source} {w}x{h} bytes={len(raw)}")

    engine = get_yolo_engine()
    print(
        f"[sahi_field] engine mode={engine.mode} model={engine.model_name} "
        f"device={getattr(engine, '_device', '?')}"
    )

    conf = 0.20

    t0 = time.time()
    fast = await engine.infer(raw, confidence=conf, frame_idx=0, time_sec=0.0)
    fast_wall = int((time.time() - t0) * 1000)

    t0 = time.time()
    sahi_512 = await engine.infer_sahi(
        raw, confidence=conf, frame_idx=0, time_sec=0.0,
        slice_height=512, slice_width=512, overlap_ratio=0.2,
    )
    s512_wall = int((time.time() - t0) * 1000)

    t0 = time.time()
    sahi_640 = await engine.infer_sahi(
        raw, confidence=conf, frame_idx=0, time_sec=0.0,
        slice_height=640, slice_width=640, overlap_ratio=0.2,
    )
    s640_wall = int((time.time() - t0) * 1000)

    fast_objs = fast.get("objects", [])
    s512_objs = sahi_512.get("objects", [])
    s640_objs = sahi_640.get("objects", [])

    fast_n = len(fast_objs)
    s512_n = len(s512_objs)
    s640_n = len(s640_objs)

    fast_small = _small_count(fast_objs)
    s512_small = _small_count(s512_objs)
    s640_small = _small_count(s640_objs)

    print(
        f"[sahi_field] fast:   n={fast_n} (small={fast_small}) ms={fast.get('ms')} wall={fast_wall}"
    )
    print(
        f"[sahi_field] sahi512: n={s512_n} (small={s512_small}) ms={sahi_512.get('ms')} wall={s512_wall} sahi={sahi_512.get('sahi')}"
    )
    print(
        f"[sahi_field] sahi640: n={s640_n} (small={s640_small}) ms={sahi_640.get('ms')} wall={s640_wall} sahi={sahi_640.get('sahi')}"
    )

    # Verdict: SAHI gain if either slice size finds more small objects than fast.
    best_sahi_small = max(s512_small, s640_small)
    if best_sahi_small > fast_small:
        verdict = "SAHI GAIN"
    elif best_sahi_small == fast_small and max(s512_n, s640_n) > fast_n:
        verdict = "SAHI GAIN (total)"
    elif best_sahi_small == fast_small:
        verdict = "NO GAIN / NEUTRAL"
    else:
        verdict = "SAHI LOSS (fast found more small objects)"

    print(f"[sahi_field] verdict: {verdict}")

    logs_dir = ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "frame_source": source,
        "frame_w": w,
        "frame_h": h,
        "frame_bytes": len(raw),
        "engine_mode": engine.mode,
        "model": engine.model_name,
        "device": getattr(engine, "_device", None),
        "confidence": conf,
        "fast": {
            "n": fast_n,
            "small": fast_small,
            "ms": fast.get("ms"),
            "wall_ms": fast_wall,
            "classes": _per_class_counts(fast_objs),
        },
        "sahi_512": {
            "n": s512_n,
            "small": s512_small,
            "ms": sahi_512.get("ms"),
            "wall_ms": s512_wall,
            "sahi_flag": sahi_512.get("sahi"),
            "classes": _per_class_counts(s512_objs),
        },
        "sahi_640": {
            "n": s640_n,
            "small": s640_small,
            "ms": sahi_640.get("ms"),
            "wall_ms": s640_wall,
            "sahi_flag": sahi_640.get("sahi"),
            "classes": _per_class_counts(s640_objs),
        },
        "delta_small_best_vs_fast": best_sahi_small - fast_small,
        "verdict": verdict,
    }
    out_path = logs_dir / "sahi_field_test.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[sahi_field] wrote {out_path}")

    ok = (
        "error" not in fast
        and "error" not in sahi_512
        and "error" not in sahi_640
        and sahi_512.get("sahi") is True
        and sahi_640.get("sahi") is True
    )
    print(f"[sahi_field] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
