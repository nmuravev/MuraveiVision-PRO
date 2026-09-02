"""Local sidecar telemetry: DJI SRT / CSV → flight track + time interpolation."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from services.db import get_flight_track, list_detections, update_detection, upsert_flight_track
from services.security import archive_root, assert_in_archive

BASE_DIR = Path(__file__).resolve().parents[2]

_SRT_BLOCK = re.compile(
    r"(?P<idx>\d+)\s*\n"
    r"(?P<t0>\d{2}:\d{2}:\d{2}[,.]\d+)\s*-->\s*(?P<t1>\d{2}:\d{2}:\d{2}[,.]\d+)\s*\n"
    r"(?P<body>.*?)(?=\n\d+\s*\n|\Z)",
    re.DOTALL | re.MULTILINE,
)

_GPS_PAREN = re.compile(
    r"GPS\s*\(\s*(?P<lat>[-+]?\d+(?:\.\d+)?)\s*,\s*(?P<lon>[-+]?\d+(?:\.\d+)?)"
    r"(?:\s*,\s*(?P<alt>[-+]?\d+(?:\.\d+)?))?\s*\)",
    re.IGNORECASE,
)
_LAT_BRACKET = re.compile(r"\[?\s*latitude\s*[:=]\s*([-+]?\d+(?:\.\d+)?)\s*\]?", re.I)
_LON_BRACKET = re.compile(r"\[?\s*longitude\s*[:=]\s*([-+]?\d+(?:\.\d+)?)\s*\]?", re.I)
_ALT_BRACKET = re.compile(
    r"\[?\s*(?:rel_alt|abs_alt|altitude|alt)\s*[:=]\s*([-+]?\d+(?:\.\d+)?)\s*\]?",
    re.I,
)
_YAW_BRACKET = re.compile(
    r"\[?\s*(?:gb_yaw|yaw|heading)\s*[:=]\s*([-+]?\d+(?:\.\d+)?)\s*\]?",
    re.I,
)


def _hms_to_sec(raw: str) -> float:
    raw = raw.strip().replace(",", ".")
    parts = raw.split(":")
    if len(parts) != 3:
        return 0.0
    h, m, s = parts
    return int(h) * 3600 + int(m) * 60 + float(s)


def _point(
    timestamp: float,
    lat: float,
    lon: float,
    alt: float | None = None,
    yaw: float | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "timestamp": float(timestamp),
        "lat": float(lat),
        "lon": float(lon),
        "alt": float(alt) if alt is not None else 0.0,
    }
    if yaw is not None:
        out["yaw"] = float(yaw)
    return out


def parse_srt(srt_path: str | Path) -> list[dict[str, Any]]:
    """Parse DJI-style SRT into track points (timestamp seconds from clip start)."""
    path = Path(srt_path)
    text = path.read_text(encoding="utf-8", errors="replace")
    points: list[dict[str, Any]] = []
    for m in _SRT_BLOCK.finditer(text):
        body = m.group("body")
        t0 = _hms_to_sec(m.group("t0"))
        lat = lon = alt = yaw = None
        gp = _GPS_PAREN.search(body)
        if gp:
            lat = float(gp.group("lat"))
            lon = float(gp.group("lon"))
            if gp.group("alt") is not None:
                alt = float(gp.group("alt"))
        else:
            lm = _LAT_BRACKET.search(body)
            om = _LON_BRACKET.search(body)
            if lm and om:
                lat = float(lm.group(1))
                lon = float(om.group(1))
        am = _ALT_BRACKET.search(body)
        if am and alt is None:
            alt = float(am.group(1))
        ym = _YAW_BRACKET.search(body)
        if ym:
            yaw = float(ym.group(1))
        if lat is None or lon is None:
            continue
        if abs(lat) < 1e-8 and abs(lon) < 1e-8:
            continue
        points.append(_point(t0, lat, lon, alt, yaw))
    points.sort(key=lambda p: p["timestamp"])
    return points


def _norm_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())


_LAT_KEYS = {"latitude", "lat", "gpslatitude", "custom.gps.lat"}
_LON_KEYS = {"longitude", "lon", "lng", "gpslongitude", "custom.gps.lon"}
_ALT_KEYS = {
    "altitude",
    "alt",
    "relalt",
    "absalt",
    "relativealtitude",
    "absolutealtitude",
    "asml",
    "altituderelative",
}
_YAW_KEYS = {"yaw", "heading", "gb_yaw", "gbyaw", "compassheading"}
_TIME_KEYS = {
    "time",
    "timestamp",
    "timebootms",
    "timems",
    "videotime",
    "ftime",
    "datetime",
    "offsettime",
}


def _pick_col(headers: list[str], aliases: set[str]) -> str | None:
    mapped = {_norm_header(h): h for h in headers}
    for a in aliases:
        key = _norm_header(a)
        if key in mapped:
            return mapped[key]
    return None


def _parse_time_cell(raw: str, row_idx: int) -> float:
    s = (raw or "").strip()
    if not s:
        return float(row_idx)
    # milliseconds since boot / epoch-ish large ints
    try:
        v = float(s.replace(",", "."))
        if v > 1e10:  # ns
            return v / 1e9
        if v > 1e6:  # ms
            return v / 1000.0
        return v
    except ValueError:
        pass
    if ":" in s:
        try:
            return _hms_to_sec(s)
        except Exception:
            return float(row_idx)
    return float(row_idx)


def parse_csv(csv_path: str | Path) -> list[dict[str, Any]]:
    """Parse DJI / ArduPilot-like CSV telemetry."""
    path = Path(csv_path)
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        return []
    headers = list(reader.fieldnames)
    lat_c = _pick_col(headers, _LAT_KEYS)
    lon_c = _pick_col(headers, _LON_KEYS)
    alt_c = _pick_col(headers, _ALT_KEYS)
    yaw_c = _pick_col(headers, _YAW_KEYS)
    time_c = _pick_col(headers, _TIME_KEYS)
    if not lat_c or not lon_c:
        raise ValueError(f"CSV без lat/lon колонок: {path.name}")

    points: list[dict[str, Any]] = []
    for i, row in enumerate(reader):
        try:
            lat = float(str(row.get(lat_c) or "").replace(",", "."))
            lon = float(str(row.get(lon_c) or "").replace(",", "."))
        except ValueError:
            continue
        if abs(lat) < 1e-8 and abs(lon) < 1e-8:
            continue
        alt = None
        if alt_c:
            try:
                alt = float(str(row.get(alt_c) or "").replace(",", "."))
            except ValueError:
                alt = None
        yaw = None
        if yaw_c:
            try:
                yaw = float(str(row.get(yaw_c) or "").replace(",", "."))
            except ValueError:
                yaw = None
        ts = _parse_time_cell(str(row.get(time_c) or "") if time_c else "", i)
        points.append(_point(ts, lat, lon, alt, yaw))
    # If times look like absolute boot ms starting far from 0, shift to start at 0
    if points:
        t0 = points[0]["timestamp"]
        if t0 > 60 and all(p["timestamp"] >= t0 - 1 for p in points[:5]):
            for p in points:
                p["timestamp"] = max(0.0, p["timestamp"] - t0)
    points.sort(key=lambda p: p["timestamp"])
    return points


def _resolve_video_abs(video_path: str) -> Path:
    raw = (video_path or "").strip()
    if not raw:
        raise ValueError("video_path пуст")
    p = Path(raw)
    if not p.is_absolute():
        cand = (
            BASE_DIR / raw
            if raw.replace("\\", "/").startswith("archive/")
            else archive_root() / raw
        )
        p = cand
    return assert_in_archive(p)


def find_sidecar(video_path: str) -> Path | None:
    """Find .SRT/.srt then .CSV/.csv next to the video (same stem)."""
    video = _resolve_video_abs(video_path)
    if not video.is_file():
        # Allow looking next to a logical path even if only sidecar exists in tests
        parent = video.parent
        stem = video.stem
    else:
        parent = video.parent
        stem = video.stem
    for ext in (".SRT", ".srt", ".CSV", ".csv"):
        cand = parent / f"{stem}{ext}"
        if cand.is_file():
            assert_in_archive(cand)
            return cand
    return None


def interpolate(track: list[dict[str, Any]], time_sec: float) -> dict[str, Any] | None:
    """Linear interpolate lat/lon/alt/(yaw) at time_sec. Outside range → nearest."""
    if not track:
        return None
    pts = sorted(track, key=lambda p: float(p["timestamp"]))
    t = float(time_sec)
    if t <= float(pts[0]["timestamp"]):
        return dict(pts[0])
    if t >= float(pts[-1]["timestamp"]):
        return dict(pts[-1])
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        ta, tb = float(a["timestamp"]), float(b["timestamp"])
        if ta <= t <= tb:
            if tb <= ta:
                return dict(a)
            u = (t - ta) / (tb - ta)
            out: dict[str, Any] = {
                "timestamp": t,
                "lat": float(a["lat"]) + u * (float(b["lat"]) - float(a["lat"])),
                "lon": float(a["lon"]) + u * (float(b["lon"]) - float(a["lon"])),
                "alt": float(a.get("alt") or 0) + u * (float(b.get("alt") or 0) - float(a.get("alt") or 0)),
            }
            if "yaw" in a or "yaw" in b:
                ya = float(a.get("yaw") or 0)
                yb = float(b.get("yaw") or ya)
                out["yaw"] = ya + u * (yb - ya)
            return out
    return dict(pts[-1])


def parse_sidecar_file(path: Path) -> list[dict[str, Any]]:
    suf = path.suffix.lower()
    if suf == ".srt":
        return parse_srt(path)
    if suf == ".csv":
        return parse_csv(path)
    raise ValueError(f"Неподдерживаемый sidecar: {path.suffix}")


def ensure_track_for_video(video_path: str) -> list[dict[str, Any]]:
    """Find sidecar, parse, upsert flight_tracks; return points (or [])."""
    raw = (video_path or "").strip()
    if not raw:
        return []
    existing = get_flight_track(raw)
    sidecar = find_sidecar(raw)
    if sidecar is None:
        return list((existing or {}).get("points") or []) if existing else []

    points = parse_sidecar_file(sidecar)
    # Prefer client path key for DB matching detections.source_video
    key = raw
    try:
        abs_v = _resolve_video_abs(raw)
        # Also store under canonical if different — primary key = caller path
        _ = abs_v
    except Exception:
        pass
    upsert_flight_track(
        video_path=key,
        track_data=points,
        source_file=str(sidecar),
    )
    return points


def load_track_points(video_path: str) -> list[dict[str, Any]]:
    row = get_flight_track(video_path)
    if row and row.get("points"):
        return list(row["points"])
    return ensure_track_for_video(video_path)


def gps_at(video_path: str, time_sec: float) -> dict[str, Any] | None:
    """Interpolate sidecar/track GPS at clip time. None if no track."""
    raw = (video_path or "").strip()
    if not raw:
        return None
    try:
        pt = interpolate(load_track_points(raw), float(time_sec))
    except Exception:
        return None
    if not pt:
        return None
    return {
        "lat": pt.get("lat"),
        "lon": pt.get("lon"),
        "alt": pt.get("alt"),
    }


def attach_gps(payload: dict[str, Any]) -> dict[str, Any]:
    """Fill gps_* on a detection payload if missing and a track exists."""
    if payload.get("gps_lat") is not None and payload.get("gps_lon") is not None:
        return payload
    src = str(payload.get("source_video") or "")
    pt = gps_at(src, float(payload.get("time_sec") or 0))
    if not pt or pt.get("lat") is None or pt.get("lon") is None:
        return payload
    payload["gps_lat"] = pt["lat"]
    payload["gps_lon"] = pt["lon"]
    if pt.get("alt") is not None:
        payload["gps_alt"] = pt["alt"]
    return payload


def backfill_detection_gps(video_path: str) -> int:
    """Persist interpolated GPS onto detections for this video that still lack it."""
    raw = (video_path or "").strip()
    if not raw:
        return 0
    try:
        track = load_track_points(raw)
    except Exception:
        return 0
    if not track:
        return 0
    rows = list_detections(source_video=raw, include_deleted=True)
    n = 0
    for row in rows:
        if row.get("gps_lat") is not None and row.get("gps_lon") is not None:
            continue
        pt = interpolate(track, float(row.get("time_sec") or 0))
        if not pt or pt.get("lat") is None or pt.get("lon") is None:
            continue
        update_detection(
            str(row["id"]),
            {
                "gps_lat": pt.get("lat"),
                "gps_lon": pt.get("lon"),
                "gps_alt": pt.get("alt"),
            },
        )
        n += 1
    return n


def track_to_jsonable(points: list[dict[str, Any]]) -> str:
    return json.dumps(points, ensure_ascii=False)
