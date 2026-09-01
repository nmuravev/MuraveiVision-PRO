"""Smoke Sprint A.1: start batch scan on LBS video (short sample), wait for done."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

VIDEO = ROOT / "archive" / "video_2026-08-25_09-17-15.mp4"
OUT = ROOT / "logs" / "smoke_batch_scan.json"


def main() -> int:
    if not VIDEO.is_file():
        print(f"[SMOKE] MISSING {VIDEO}")
        return 2

    import importlib

    importlib.import_module("main")
    from services import batch_scanner
    from services.db import list_detections

    # Fast smoke: ~0.2 fps sample → fewer frames
    st = batch_scanner.start(
        video_path=str(VIDEO),
        fps_sample=0.2,
        conf=0.25,
        save_crops=True,
    )
    print(f"[SMOKE] started {st}")
    t0 = time.time()
    last = ""
    while True:
        cur = batch_scanner.status()
        msg = str(cur.get("message") or "")
        if msg != last:
            print(
                f"[SMOKE] {cur.get('status')} processed={cur.get('processed')} "
                f"found={cur.get('detections_found')} {msg}"
            )
            last = msg
        if cur.get("status") in ("done", "error", "idle") and cur.get("status") != "running":
            if cur.get("status") == "running":
                continue
            # wait until thread finishes emitting done
            if cur.get("status") in ("done", "error"):
                break
            if time.time() - t0 > 5 and cur.get("status") == "idle":
                break
        if time.time() - t0 > 600:
            batch_scanner.stop()
            print("[SMOKE] TIMEOUT")
            return 3
        time.sleep(0.5)

    final = batch_scanner.status()
    src = str(final.get("source_video") or VIDEO.as_posix())
    rows = [r for r in list_detections(src, include_deleted=False) if r.get("origin") == "batch_scan"]
    # also try absolute / relative variants
    if not rows:
        rows = [
            r
            for r in list_detections(include_deleted=False)
            if r.get("origin") == "batch_scan"
            and VIDEO.name in str(r.get("source_video") or "")
        ]
    payload = {
        "status": final,
        "batch_scan_rows": len(rows),
        "sample": rows[:5],
        "ok": final.get("status") == "done" and int(final.get("detections_found") or 0) >= 0,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SMOKE] wrote {OUT} rows={len(rows)} status={final.get('status')}")
    return 0 if final.get("status") == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
