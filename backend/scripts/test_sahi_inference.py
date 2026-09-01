"""Verify SAHI inference path: compare fast vs sliced detection on a sample frame.

Follows the smoke_* script conventions. Loads a frame from archive/ (or a
generated dummy), runs engine.infer() and engine.infer_sahi(), prints detection
counts + latency, and writes JSON to logs/sahi_test.json.

Run:
    muravei_env\\Scripts\\python.exe backend\\scripts\\test_sahi_inference.py
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


def _find_sample_frame() -> bytes | None:
    """Pick the first jpg/png under archive/ (shallow then 1-level deep)."""
    archive = ROOT / "archive"
    if not archive.is_dir():
        return None
    for pat in ("*.jpg", "*.jpeg", "*.png"):
        for p in sorted(archive.glob(pat)):
            return p.read_bytes()
        for p in sorted(archive.rglob(pat)):
            return p.read_bytes()
    return None


def _dummy_frame() -> bytes:
    """Generate a 1280x720 noise JPEG so the script runs without a real frame."""
    from PIL import Image
    import numpy as np

    arr = (np.random.rand(720, 1280, 3) * 255).astype("uint8")
    img = Image.fromarray(arr, "RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


async def main() -> int:
    import main  # noqa: F401  (initializes BASE_DIR / settings)
    from services.yolo_engine import get_yolo_engine

    raw = _find_sample_frame()
    source = "archive"
    if not raw:
        raw = _dummy_frame()
        source = "dummy-1280x720"
    print(f"[sahi_test] frame source={source} bytes={len(raw)}")

    engine = get_yolo_engine()
    print(f"[sahi_test] engine mode={engine.mode} model={engine.model_name} device={engine._device}")

    t0 = time.time()
    fast = await engine.infer(raw, confidence=0.20, frame_idx=0, time_sec=0.0)
    fast_ms = int((time.time() - t0) * 1000)

    t0 = time.time()
    sahi = await engine.infer_sahi(
        raw, confidence=0.20, frame_idx=0, time_sec=0.0,
        slice_height=512, slice_width=512, overlap_ratio=0.2,
    )
    sahi_ms = int((time.time() - t0) * 1000)

    fast_n = len(fast.get("objects", []))
    sahi_n = len(sahi.get("objects", []))
    print(
        f"[sahi_test] fast: n={fast_n} ms={fast.get('ms')} "
        f"| sahi: n={sahi_n} ms={sahi.get('ms')} sahi_flag={sahi.get('sahi')}"
    )
    print(f"[sahi_test] wall fast_ms={fast_ms} sahi_ms={sahi_ms}")

    logs_dir = ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "frame_source": source,
        "frame_bytes": len(raw),
        "engine_mode": engine.mode,
        "model": engine.model_name,
        "device": engine._device,
        "fast": {"n": fast_n, "ms": fast.get("ms"), "wall_ms": fast_ms},
        "sahi": {"n": sahi_n, "ms": sahi.get("ms"), "wall_ms": sahi_ms, "flag": sahi.get("sahi")},
    }
    (logs_dir / "sahi_test.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"[sahi_test] wrote {logs_dir / 'sahi_test.json'}")

    # Pass if SAHI path ran without error (does not assert SAHI finds more).
    ok = "error" not in sahi and sahi.get("sahi") is True
    print(f"[sahi_test] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
