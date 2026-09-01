"""Field REC acceptance: recording process stays alive and writes for >60 seconds."""
from __future__ import annotations

import os
import time
from pathlib import Path

import cv2
import httpx

ROOT = Path(__file__).resolve().parents[2]
BASE = os.environ.get("MURAVEI_SMOKE_BASE", "http://127.0.0.1:8000")
DRONE_ID = "smoke-rec-60s"


def _long_video() -> Path:
    candidates = sorted((ROOT / "archive").rglob("*.mp4"), key=lambda p: p.stat().st_size, reverse=True)
    for path in candidates:
        cap = cv2.VideoCapture(str(path))
        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
            frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if fps > 0 and frames / fps >= 70:
                return path
        finally:
            cap.release()
    raise RuntimeError("No archive MP4 at least 70 seconds long")


def main() -> int:
    source = _long_video()
    with httpx.Client(timeout=20.0) as client:
        login = client.post(f"{BASE}/api/auth/login", json={"pin": "1234567"})
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        start = client.post(
            f"{BASE}/api/rec/start",
            headers=headers,
            json={"drone_id": DRONE_ID, "source_path": str(source), "start_sec": 0},
        )
        start.raise_for_status()
        path = Path(start.json()["path"])
        try:
            time.sleep(61)
            status = client.get(
                f"{BASE}/api/rec/status",
                headers=headers,
                params={"drone_id": DRONE_ID},
            )
            status.raise_for_status()
            payload = status.json()
            if not payload.get("recording"):
                raise RuntimeError(f"REC stopped before 60s: {payload}")
        finally:
            stop = client.post(
                f"{BASE}/api/rec/stop",
                headers=headers,
                json={"drone_id": DRONE_ID},
            )
            stop.raise_for_status()
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"REC output missing or empty: {path}")
        print(f"REC_60S_GREEN source={source.name} bytes={path.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
