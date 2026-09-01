"""Smoke: run YOLO on sample frames from archive video. Uses muravei_env only."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

VIDEO = ROOT / "archive" / "video_2026-08-25_09-17-15.mp4"
OUT = ROOT / "logs" / "smoke_video_2026-08-25.json"


def grab_frames(path: Path, times_sec: list[float]) -> list[tuple[float, bytes]]:
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = nframes / fps if fps > 0 else 0.0
    print(f"[SMOKE] video={path.name} fps={fps:.2f} frames={nframes} dur={dur:.1f}s")
    out: list[tuple[float, bytes]] = []
    for t in times_sec:
        if dur > 0:
            t = max(0.0, min(t, max(0.0, dur - 0.05)))
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            print(f"[SMOKE] skip t={t:.2f} (read fail)")
            continue
        ok_enc, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok_enc:
            continue
        out.append((t, buf.tobytes()))
    cap.release()
    return out


def main() -> int:
    if not VIDEO.is_file():
        print(f"[SMOKE] MISSING {VIDEO}")
        return 2

    # Load FastAPI app first to avoid circular import (classes ↔ main ↔ yolo_engine)
    import importlib

    importlib.import_module("main")
    from services.yolo_engine import get_yolo_engine

    engine = get_yolo_engine()
    snap = engine.status_snapshot()
    print(
        f"[SMOKE] engine mode={snap.get('mode')} model={snap.get('model')} "
        f"kind={snap.get('kind')} device={snap.get('device')} tier={snap.get('tier')}"
    )

    # Sample across the clip
    times = [0.5, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0]
    frames = grab_frames(VIDEO, times)
    if not frames:
        print("[SMOKE] no frames extracted")
        return 3

    results = []
    for i, (t, jpeg) in enumerate(frames):
        t0 = time.time()
        res = engine._predict_sync(jpeg, 0.35, i, t, viewer_id="smoke-1")  # noqa: SLF001
        wall = int((time.time() - t0) * 1000)
        objs = res.get("objects") or []
        summary = {
            "time_sec": t,
            "ms": res.get("ms"),
            "wall_ms": wall,
            "kind": res.get("kind"),
            "n": res.get("n"),
            "ego": res.get("ego"),
            "nms_mode": res.get("nms_mode"),
            "classes": [o.get("class_en") for o in objs],
            "tracks": [o.get("track_id") for o in objs],
            "motions": [o.get("motion") for o in objs[:6]],
            "error": res.get("error"),
        }
        results.append(summary)
        print(
            f"[SMOKE] t={t:5.1f}s  n={summary['n']}  ms={summary['ms']}  "
            f"kind={summary['kind']}  classes={summary['classes'][:8]}"
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "video": str(VIDEO),
        "engine": snap,
        "frames": results,
        "total_objects": sum(int(r["n"] or 0) for r in results),
        "any_detections": any(int(r["n"] or 0) > 0 for r in results),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SMOKE] wrote {OUT}")
    print(
        f"[SMOKE] DONE total_objects={payload['total_objects']} "
        f"any_detections={payload['any_detections']}"
    )
    return 0 if snap.get("mode") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
