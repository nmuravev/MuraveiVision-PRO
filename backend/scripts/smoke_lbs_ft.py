"""Force-load yolo26n-ft.pt and smoke-test LBS archive video."""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

VIDEO = ROOT / "archive" / "video_2026-08-25_09-17-15.mp4"
FT = ROOT / "assets" / "models" / "yolo26n-ft.pt"
OUT = ROOT / "logs" / "smoke_lbs_ft.json"
CONF = 0.20


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
            t = max(0.0, min(float(t), max(0.0, dur - 0.05)))
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
    if not FT.is_file():
        print(f"[SMOKE] MISSING {FT}")
        return 2

    import importlib

    importlib.import_module("main")
    from services.yolo_engine import get_yolo_engine

    engine = get_yolo_engine()
    ok = engine.force_load(FT)
    if not ok:
        print("[SMOKE] force_load yolo26n-ft.pt FAILED")
        return 1

    snap = engine.status_snapshot()
    print(
        f"[SMOKE] ACTIVE model={snap.get('model')} kind={snap.get('kind')} "
        f"mode={snap.get('mode')} device={snap.get('device')} "
        f"nc={len(getattr(engine, '_names', {}) or {})}"
    )
    if snap.get("model") != "yolo26n-ft.pt":
        print(f"[SMOKE] FAIL: expected yolo26n-ft.pt, got {snap.get('model')}")
        return 1

    # Dense sample across ~9 min LBS flight
    times = [
        5,
        30,
        60,
        90,
        120,
        150,
        180,
        210,
        240,
        270,
        300,
        330,
        360,
        390,
        420,
        450,
        480,
        510,
        530,
    ]
    frames = grab_frames(VIDEO, times)
    if not frames:
        print("[SMOKE] no frames")
        return 3

    hist: Counter[str] = Counter()
    results = []
    for i, (t, jpeg) in enumerate(frames):
        t0 = time.time()
        res = engine._predict_sync(jpeg, CONF, i, t, viewer_id="smoke-lbs-ft")  # noqa: SLF001
        wall = int((time.time() - t0) * 1000)
        objs = res.get("objects") or []
        classes = [str(o.get("class_en") or "") for o in objs]
        for c in classes:
            hist[c] += 1
        row = {
            "time_sec": t,
            "ms": res.get("ms"),
            "wall_ms": wall,
            "kind": res.get("kind"),
            "n": res.get("n"),
            "classes": classes[:20],
            "confs": [round(float(o.get("confidence") or 0), 3) for o in objs[:12]],
            "error": res.get("error"),
        }
        results.append(row)
        print(
            f"[SMOKE] t={t:6.1f}s  n={row['n']:3}  ms={row['ms']}  "
            f"classes={row['classes'][:8]}"
        )

    payload = {
        "video": str(VIDEO),
        "forced_model": str(FT),
        "conf": CONF,
        "engine": snap,
        "nc": len(getattr(engine, "_names", {}) or {}),
        "frames": results,
        "class_hist": dict(hist.most_common(40)),
        "total_objects": sum(int(r["n"] or 0) for r in results),
        "any_detections": any(int(r["n"] or 0) > 0 for r in results),
        "frames_with_hits": sum(1 for r in results if int(r["n"] or 0) > 0),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SMOKE] wrote {OUT}")
    print(
        f"[SMOKE] DONE model=yolo26n-ft.pt total={payload['total_objects']} "
        f"hits_frames={payload['frames_with_hits']}/{len(results)} "
        f"top={hist.most_common(10)}"
    )
    return 0 if payload["any_detections"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
