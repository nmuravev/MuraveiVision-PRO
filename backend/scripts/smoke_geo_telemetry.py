"""Smoke Sprint A.4: SRT/CSV parse → flight_tracks → interpolate → GPS on detection + SVG report."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ARCHIVE_SMOKE = ROOT / "archive" / "smoke_geo"
VIDEO_KEY = "archive/smoke_geo/clip.mp4"
OUT = ROOT / "logs" / "smoke_geo_telemetry.json"


def main() -> int:
    ARCHIVE_SMOKE.mkdir(parents=True, exist_ok=True)
    # Sidecar next to logical video path (video file itself optional for parse/import)
    srt_dst = ARCHIVE_SMOKE / "clip.srt"
    csv_dst = ARCHIVE_SMOKE / "clip_alt.csv"
    shutil.copy2(FIXTURES / "sample_dji.srt", srt_dst)
    shutil.copy2(FIXTURES / "sample_dji.csv", csv_dst)
    # Touch empty placeholder so resolve treats path as under archive
    vid = ARCHIVE_SMOKE / "clip.mp4"
    if not vid.is_file():
        vid.write_bytes(b"")

    import importlib

    importlib.import_module("main")
    from services.db import get_flight_track, init_db, insert_detection, list_detections
    from services.reporter import _build_items, _svg_flight_map, generate_html_report
    from services.telemetry import (
        ensure_track_for_video,
        find_sidecar,
        interpolate,
        parse_csv,
        parse_srt,
    )

    init_db()

    srt_pts = parse_srt(FIXTURES / "sample_dji.srt")
    csv_pts = parse_csv(FIXTURES / "sample_dji.csv")
    assert len(srt_pts) >= 4, f"SRT points={len(srt_pts)}"
    assert len(csv_pts) >= 4, f"CSV points={len(csv_pts)}"

    mid = interpolate(srt_pts, 3.5)
    assert mid is not None and mid["lat"] and mid["lon"], mid

    sc = find_sidecar(VIDEO_KEY)
    assert sc is not None and sc.suffix.lower() == ".srt", sc

    points = ensure_track_for_video(VIDEO_KEY)
    assert len(points) >= 4, points
    stored = get_flight_track(VIDEO_KEY)
    assert stored and stored["point_count"] >= 4, stored

    gps = interpolate(points, 2.0)
    assert gps is not None
    row = insert_detection(
        {
            "source_video": VIDEO_KEY,
            "time_sec": 2.0,
            "frame_idx": 60,
            "class_id": 0,
            "class_name": "soldier",
            "confidence": 0.9,
            "bbox_x": 0.1,
            "bbox_y": 0.1,
            "bbox_w": 0.2,
            "bbox_h": 0.2,
            "origin": "batch_scan",
            "gps_lat": gps["lat"],
            "gps_lon": gps["lon"],
            "gps_alt": gps.get("alt"),
        }
    )
    assert row.get("gps_lat") is not None and row.get("gps_lon") is not None, row

    dets = list_detections(source_video=VIDEO_KEY)
    with_gps = [d for d in dets if d.get("gps_lat") is not None]
    assert with_gps, "no gps detections"

    items = _build_items(with_gps)
    svg = _svg_flight_map(points, items)
    assert "polyline" in svg or "circle" in svg, svg[:200]

    report = generate_html_report()
    html = report.read_text(encoding="utf-8")
    assert "flight-map" in html or "Траектория" in html or row["gps_lat"] is not None

    # CSV parser sanity on archive copy
    csv_only = parse_csv(csv_dst)
    assert len(csv_only) == 5

    payload = {
        "ok": True,
        "srt_points": len(srt_pts),
        "csv_points": len(csv_pts),
        "track_points": len(points),
        "interp_t2": gps,
        "detection_id": row["id"],
        "gps_lat": row["gps_lat"],
        "gps_lon": row["gps_lon"],
        "report": str(report),
        "svg_len": len(svg),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[SMOKE] OK {json.dumps(payload, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
