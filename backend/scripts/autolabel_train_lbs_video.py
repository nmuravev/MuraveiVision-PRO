"""Auto-label LBS video → SQLite crops → detect-only finetune.

Uses muravei_env Python only.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

VIDEO = ROOT / "archive" / "video_2026-08-25_09-17-15.mp4"
# Store as project-relative path (same style as MediaPool drops)
SOURCE_KEY = "archive/video_2026-08-25_09-17-15.mp4"
OUT_JSON = ROOT / "logs" / "autolabel_train_2026-08-25.json"
STEP_SEC = 6.0
CONF = 0.14
EPOCHS = 12
MAX_PER_FRAME = 12
MIN_BOX_AREA = 0.0008
MAX_BOX_AREA = 0.50


def _iou(a: dict, b: dict) -> float:
    ax1, ay1, ax2, ay2 = a["x1"], a["y1"], a["x2"], a["y2"]
    bx1, by1, bx2, by2 = b["x1"], b["y1"], b["x2"], b["y2"]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    aa = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    ba = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    u = aa + ba - inter
    return inter / u if u > 0 else 0.0


def _dedupe(objs: list[dict]) -> list[dict]:
    ordered = sorted(objs, key=lambda o: float(o.get("confidence") or 0), reverse=True)
    kept: list[dict] = []
    for o in ordered:
        if any(
            o.get("class_en") == k.get("class_en") and _iou(o["bbox"], k["bbox"]) >= 0.45
            for k in kept
        ):
            continue
        kept.append(o)
        if len(kept) >= MAX_PER_FRAME:
            break
    return kept


def main() -> int:
    import importlib

    import cv2

    importlib.import_module("main")
    from services.classes import invalidate_class_cache
    from services.db import insert_detection, list_detections, save_crop_jpeg
    from services.trainer import start, status, drain_events
    from services.yolo_engine import get_yolo_engine

    invalidate_class_cache()
    # Force fresh engine in this process
    import services.yolo_engine as ye

    ye._engine = None  # noqa: SLF001

    if not VIDEO.is_file():
        print(f"MISSING {VIDEO}")
        return 2

    eng = get_yolo_engine()
    print(f"[AUTO] model={eng.model_name} kind={eng.kind} device={eng._device}")  # noqa: SLF001

    cap = cv2.VideoCapture(str(VIDEO))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25)
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = nframes / fps if fps else 0
    print(f"[AUTO] video dur={dur:.1f}s step={STEP_SEC}s")

    times = []
    t = 1.0
    while t < max(1.0, dur - 1.0):
        times.append(t)
        t += STEP_SEC

    saved = 0
    class_counts: Counter[str] = Counter()
    frame_hits = 0
    details: list[dict] = []

    for i, tsec in enumerate(times):
        cap.set(cv2.CAP_PROP_POS_MSEC, tsec * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        ok_enc, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if not ok_enc:
            continue
        jpeg = buf.tobytes()
        res = eng._predict_sync(jpeg, CONF, i, tsec, viewer_id="autolabel")  # noqa: SLF001
        objs = []
        for o in res.get("objects") or []:
            bbox = o.get("bbox") or {}
            area = max(0.0, (bbox["x2"] - bbox["x1"]) * (bbox["y2"] - bbox["y1"]))
            if area < MIN_BOX_AREA or area > MAX_BOX_AREA:
                continue
            objs.append(o)
        objs = _dedupe(objs)
        if objs:
            frame_hits += 1
        for o in objs:
            det_id = str(uuid.uuid4())
            x1, y1, x2, y2 = o["bbox"]["x1"], o["bbox"]["y1"], o["bbox"]["x2"], o["bbox"]["y2"]
            xywh = {"x": x1, "y": y1, "w": max(0.001, x2 - x1), "h": max(0.001, y2 - y1)}
            crop_path = save_crop_jpeg(det_id, jpeg, xywh)
            if not crop_path:
                continue
            class_en = str(o.get("class_en") or "unknown")
            row = insert_detection(
                {
                    "id": det_id,
                    "source_video": SOURCE_KEY,
                    "time_sec": float(tsec),
                    "frame_idx": int(tsec * fps),
                    "class_id": int(o.get("class_id") or 0),
                    "class_name": class_en,
                    "confidence": float(o.get("confidence") or 0),
                    "bbox_x": xywh["x"],
                    "bbox_y": xywh["y"],
                    "bbox_w": xywh["w"],
                    "bbox_h": xywh["h"],
                    "crop_path": crop_path,
                    "origin": "auto",
                    "user_notes": f"autolabel {VIDEO.name}",
                    "is_edited": 0,
                }
            )
            saved += 1
            class_counts[class_en] += 1
            details.append(
                {
                    "id": det_id,
                    "t": round(tsec, 2),
                    "class": class_en,
                    "conf": round(float(o.get("confidence") or 0), 3),
                }
            )
        if (i + 1) % 10 == 0 or objs:
            print(
                f"[AUTO] {i+1}/{len(times)} t={tsec:.1f}s n={len(objs)} "
                f"saved_total={saved} {[o.get('class_en') for o in objs[:6]]}"
            )

    cap.release()
    print(f"[AUTO] frames_with_hits={frame_hits}/{len(times)} saved={saved}")
    print(f"[AUTO] classes: {dict(class_counts)}")

    # Count crops for this source
    rows = [d for d in list_detections(include_deleted=False) if d.get("source_video") == SOURCE_KEY]
    print(f"[AUTO] DB rows for source={len(rows)}")

    payload = {
        "video": str(VIDEO),
        "source_key": SOURCE_KEY,
        "model": eng.model_name,
        "kind": eng.kind,
        "saved": saved,
        "class_counts": dict(class_counts),
        "samples": len(times),
        "frame_hits": frame_hits,
        "details": details[:200],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if saved < 3:
        print("[AUTO] not enough crops to train (<3)")
        return 3

    print(f"[TRAIN] starting epochs={EPOCHS} source={SOURCE_KEY}")
    start(epochs=EPOCHS, source_video=SOURCE_KEY)
    idx = 0
    while True:
        st = status()
        events, idx = drain_events(idx)
        for ev in events:
            msg = ev.get("message") or ev.get("error") or ""
            print(
                f"[TRAIN] {ev.get('status', st.get('status'))} "
                f"epoch={ev.get('epoch', st.get('epoch'))}/{ev.get('epochs', st.get('epochs'))} "
                f"{msg}"
            )
        if st.get("status") in {"done", "error", "idle"} and st.get("status") != "running":
            # wait until thread truly finished
            if st.get("status") == "running":
                time.sleep(1)
                continue
            if st.get("finished_at") or st.get("status") in {"done", "error"}:
                # still running briefly after message
                pass
        if st.get("status") == "done":
            print(f"[TRAIN] SUCCESS {st.get('message')}")
            payload["train"] = st
            OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return 0
        if st.get("status") == "error":
            print(f"[TRAIN] FAILED {st.get('error')}")
            payload["train"] = st
            OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return 4
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
