"""Smoke Sprint B.1: geo query API + track load for Flight3D data path (muravei_env)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

VIDEO = "archive/smoke_geo/clip.mp4"
OUT = ROOT / "logs" / "smoke_flight3d.json"


def main() -> int:
    import importlib

    importlib.import_module("main")
    from fastapi.testclient import TestClient
    from main import app
    from services.db import init_db
    from services.telemetry import ensure_track_for_video, interpolate

    init_db()
    points = ensure_track_for_video(VIDEO)
    assert points, "expected smoke_geo clip.srt track"

    # Local projection sanity (mirror frontend formula)
    lat0 = sum(p["lat"] for p in points) / len(points)
    lon0 = sum(p["lon"] for p in points) / len(points)
    R = 6378137.0
    import math

    def to_local(lat: float, lon: float, alt: float) -> tuple[float, float, float]:
        d_lat = math.radians(lat - lat0)
        d_lon = math.radians(lon - lon0)
        x = d_lon * math.cos(math.radians(lat0)) * R
        z = -d_lat * R
        y = alt
        return x, y, z

    xs = [to_local(p["lat"], p["lon"], float(p.get("alt") or 0))[0] for p in points]
    assert max(xs) - min(xs) > 1.0, "track should span metres"

    mid = interpolate(points, 2.0)
    assert mid and mid["lat"]

    client = TestClient(app)
    # Login as operator
    login = client.post("/api/auth/login", json={"pin": "1234567"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    tr = client.get("/api/geo/track", params={"video_path": VIDEO}, headers=headers)
    assert tr.status_code == 200, tr.text
    assert tr.json()["point_count"] >= 4

    det = client.get("/api/geo/detections", params={"video_path": VIDEO}, headers=headers)
    assert det.status_code == 200, det.text

    # Path form still works for relative archive paths
    tr2 = client.get(f"/api/geo/track/{VIDEO}", headers=headers)
    assert tr2.status_code == 200, tr2.text

    payload = {
        "ok": True,
        "track_points": tr.json()["point_count"],
        "detections": det.json().get("count"),
        "interp": mid,
        "span_m_x": max(xs) - min(xs),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[SMOKE] OK {json.dumps(payload, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
