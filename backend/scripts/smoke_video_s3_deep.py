"""Deeper smoke: evenly sample full clip + raw vs filtered detections."""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

VIDEO = ROOT / "archive" / "video_2026-08-25_09-17-15.mp4"
OUT = ROOT / "logs" / "smoke_video_2026-08-25_deep.json"


def main() -> int:
    import importlib

    import cv2
    import numpy as np
    from PIL import Image

    importlib.import_module("main")
    from services.yolo_engine import COCO_FALLBACK_CONF, get_yolo_engine

    if not VIDEO.is_file():
        print("MISSING video")
        return 2

    eng = get_yolo_engine()
    print(
        f"engine model={eng.model_name} kind={eng.kind} device={eng._device} "  # noqa: SLF001
        f"names={eng._names}"  # noqa: SLF001
    )

    cap = cv2.VideoCapture(str(VIDEO))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25)
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = nframes / fps if fps else 0
    print(f"video dur={dur:.1f}s fps={fps:.2f} frames={nframes}")

    # 12 samples across full duration
    times = [dur * (i + 0.5) / 12 for i in range(12)] if dur > 1 else [0.5]
    rows = []
    hits = 0

    for i, t in enumerate(times):
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0, t) * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        ok_enc, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok_enc:
            continue
        jpeg = buf.tobytes()

        # Pipeline (catalog-filtered) — soft LBS floor
        res = eng._predict_sync(jpeg, 0.18, i, t, viewer_id="smoke-deep")  # noqa: SLF001
        objs = res.get("objects") or []

        # Raw primary predict (no catalog filter) for diagnosis
        raw_labels: list[str] = []
        try:
            img = Image.open(io.BytesIO(jpeg)).convert("RGB")
            pred = eng.model.predict(
                source=img,
                imgsz=getattr(eng, "_imgsz", 1024),
                conf=0.15,
                verbose=False,
                device=eng._device,  # noqa: SLF001
            )
            if pred and pred[0].boxes is not None and len(pred[0].boxes):
                names = pred[0].names or eng._names  # noqa: SLF001
                for box in pred[0].boxes:
                    cid = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                    if isinstance(names, dict):
                        lab = str(names.get(cid, names.get(str(cid), cid)))
                    else:
                        lab = str(cid)
                    raw_labels.append(f"{lab}:{conf:.2f}")
        except Exception as exc:  # noqa: BLE001
            raw_labels = [f"ERR:{exc}"]

        # Raw COCO fallback if available
        coco_labels: list[str] = []
        try:
            fb = eng._ensure_fallback()  # noqa: SLF001
            if fb is not None:
                img = Image.open(io.BytesIO(jpeg)).convert("RGB")
                pred = fb.predict(
                    source=img,
                    imgsz=getattr(eng, "_imgsz", 1024),
                    conf=COCO_FALLBACK_CONF,
                    verbose=False,
                    device=eng._device,  # noqa: SLF001
                )
                if pred and pred[0].boxes is not None and len(pred[0].boxes):
                    names = pred[0].names or {}
                    for box in pred[0].boxes:
                        cid = int(box.cls[0].item())
                        conf = float(box.conf[0].item())
                        lab = str(names.get(cid, names.get(str(cid), cid))) if isinstance(names, dict) else str(cid)
                        coco_labels.append(f"{lab}:{conf:.2f}")
        except Exception as exc:  # noqa: BLE001
            coco_labels = [f"ERR:{exc}"]

        if objs:
            hits += 1
        row = {
            "t": round(t, 2),
            "pipeline_n": len(objs),
            "pipeline_classes": [o.get("class_en") for o in objs],
            "pipeline_ms": res.get("ms"),
            "kind": res.get("kind"),
            "raw_primary": raw_labels[:12],
            "raw_coco": coco_labels[:12],
            "ego": res.get("ego"),
        }
        rows.append(row)
        print(
            f"t={t:6.1f}s pipe={len(objs):2d} {row['pipeline_classes'][:5]} | "
            f"raw_ft={raw_labels[:5]} | coco={coco_labels[:5]}"
        )

    cap.release()
    payload = {
        "video": str(VIDEO),
        "duration_sec": dur,
        "model": eng.model_name,
        "kind": eng.kind,
        "device": eng._device,  # noqa: SLF001
        "hits_pipeline": hits,
        "samples": len(rows),
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDONE hits={hits}/{len(rows)} → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
