"""P3.15.2: Auto time sync between Before/After videos (GPS tracks → detections fallback)."""
from __future__ import annotations

from typing import Any, Literal

from services.change_detection import haversine_m

_MIN_GPS_PAIRS = 5
_DEFAULT_TOLERANCE_M = 15.0
_CLASS_TOLERANCE = 0.15
_MAX_GAP_SEC = 2.0
_SMOOTH_WINDOW = 3


def _normalize_track_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in points or []:
        try:
            t = p.get("timestamp", p.get("time_sec"))
            lat = p.get("lat", p.get("gps_lat"))
            lon = p.get("lon", p.get("gps_lon"))
            if t is None or lat is None or lon is None:
                continue
            item: dict[str, Any] = {
                "time_sec": float(t),
                "lat": float(lat),
                "lon": float(lon),
            }
            alt = p.get("alt", p.get("gps_alt"))
            if alt is not None:
                item["alt"] = float(alt)
            out.append(item)
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda x: x["time_sec"])
    return out


def _smooth_track(points: list[dict[str, Any]], window: int = _SMOOTH_WINDOW) -> list[dict[str, Any]]:
    if window < 2 or len(points) < window:
        return list(points)
    half = window // 2
    smoothed: list[dict[str, Any]] = []
    n = len(points)
    for i, p in enumerate(points):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        chunk = points[lo:hi]
        lat = sum(c["lat"] for c in chunk) / len(chunk)
        lon = sum(c["lon"] for c in chunk) / len(chunk)
        item = {**p, "lat": lat, "lon": lon}
        if all("alt" in c for c in chunk):
            item["alt"] = sum(float(c["alt"]) for c in chunk) / len(chunk)
        smoothed.append(item)
    return smoothed


def sync_by_gps_track(
    track_before: list[dict[str, Any]],
    track_after: list[dict[str, Any]],
    *,
    tolerance_m: float = _DEFAULT_TOLERANCE_M,
) -> dict[str, Any]:
    before = _smooth_track(_normalize_track_points(track_before))
    after = _smooth_track(_normalize_track_points(track_after))
    pairs: list[dict[str, Any]] = []
    if not before or not after:
        return {"method": "gps", "pairs": [], "segments": []}

    for b in before:
        best: dict[str, Any] | None = None
        best_d = float("inf")
        for a in after:
            d = haversine_m(b["lat"], b["lon"], a["lat"], a["lon"])
            if d < best_d:
                best_d = d
                best = a
        if best is not None and best_d <= tolerance_m:
            pairs.append(
                {
                    "time_before": b["time_sec"],
                    "time_after": best["time_sec"],
                    "distance_m": round(best_d, 2),
                    "lat": b["lat"],
                    "lon": b["lon"],
                }
            )

    pairs.sort(key=lambda p: p["time_before"])
    segments = group_into_segments(pairs)
    return {"method": "gps", "pairs": pairs, "segments": segments}


def _det_center(det: dict[str, Any]) -> tuple[float, float] | None:
    try:
        if "bbox_x" in det:
            x = float(det.get("bbox_x") or 0)
            y = float(det.get("bbox_y") or 0)
            w = float(det.get("bbox_w") or 0)
            h = float(det.get("bbox_h") or 0)
            return x + w / 2.0, y + h / 2.0
        bbox = det.get("bbox") or {}
        x1 = float(bbox.get("x1", 0))
        y1 = float(bbox.get("y1", 0))
        x2 = float(bbox.get("x2", 0))
        y2 = float(bbox.get("y2", 0))
        return (x1 + x2) / 2.0, (y1 + y2) / 2.0
    except (TypeError, ValueError):
        return None


def sync_by_detections(
    dets_before: list[dict[str, Any]],
    dets_after: list[dict[str, Any]],
    *,
    class_tolerance: float = _CLASS_TOLERANCE,
) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    used_after: set[int] = set()

    for b in dets_before or []:
        b_cls = b.get("class_name")
        b_c = _det_center(b)
        if b_cls is None or b_c is None:
            continue
        try:
            b_t = float(b.get("time_sec") or 0)
        except (TypeError, ValueError):
            continue
        best_i: int | None = None
        best_score = float("inf")
        for ai, a in enumerate(dets_after or []):
            if ai in used_after:
                continue
            if a.get("class_name") != b_cls:
                continue
            a_c = _det_center(a)
            if a_c is None:
                continue
            dx = abs(b_c[0] - a_c[0])
            dy = abs(b_c[1] - a_c[1])
            if dx > class_tolerance or dy > class_tolerance:
                continue
            score = dx + dy
            if score < best_score:
                best_score = score
                best_i = ai
        if best_i is None:
            continue
        used_after.add(best_i)
        a = dets_after[best_i]
        try:
            a_t = float(a.get("time_sec") or 0)
        except (TypeError, ValueError):
            continue
        conf_b = float(b.get("confidence") or 0)
        conf_a = float(a.get("confidence") or 0)
        pairs.append(
            {
                "time_before": b_t,
                "time_after": a_t,
                "class_name": b_cls,
                "conf": round((conf_b + conf_a) / 2.0, 3),
                "distance_m": None,
            }
        )

    pairs.sort(key=lambda p: p["time_before"])
    segments = group_into_segments(pairs)
    return {"method": "detections", "pairs": pairs, "segments": segments}


def group_into_segments(
    pairs: list[dict[str, Any]],
    *,
    max_gap_sec: float = _MAX_GAP_SEC,
) -> list[dict[str, Any]]:
    if not pairs:
        return []
    ordered = sorted(pairs, key=lambda p: float(p["time_before"]))
    segments: list[dict[str, Any]] = []
    cur = [ordered[0]]

    def flush(group: list[dict[str, Any]]) -> None:
        if not group:
            return
        segments.append(
            {
                "start_before": float(group[0]["time_before"]),
                "end_before": float(group[-1]["time_before"]),
                "start_after": float(group[0]["time_after"]),
                "end_after": float(group[-1]["time_after"]),
                "pair_count": len(group),
            }
        )

    for p in ordered[1:]:
        prev = cur[-1]
        if abs(float(p["time_before"]) - float(prev["time_before"])) <= max_gap_sec:
            cur.append(p)
        else:
            flush(cur)
            cur = [p]
    flush(cur)
    return segments


def _track_points_from_row(row: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not row:
        return []
    pts = row.get("points")
    return pts if isinstance(pts, list) else []


def _resolve_source_keys(video_before: str, video_after: str) -> tuple[str, str]:
    from services.batch_scanner import _resolve_video

    _, source_before = _resolve_video(video_before)
    _, source_after = _resolve_video(video_after)
    return source_before, source_after


def _load_track_points(source_video: str) -> list[dict[str, Any]]:
    from services.db import get_flight_track

    return _track_points_from_row(get_flight_track(source_video))


def _load_detections(source_video: str) -> list[dict[str, Any]]:
    from services.db import list_detections

    return list_detections(source_video=source_video)


def auto_sync(
    video_before: str,
    video_after: str,
    *,
    source: Literal["auto", "tracks", "detections"] = "auto",
    tolerance_m: float = _DEFAULT_TOLERANCE_M,
) -> dict[str, Any]:
    source_before, source_after = _resolve_source_keys(video_before, video_after)

    try_tracks = source in ("auto", "tracks")
    try_dets = source in ("auto", "detections")

    if try_tracks:
        track_b = _load_track_points(source_before)
        track_a = _load_track_points(source_after)
        if track_b and track_a:
            gps = sync_by_gps_track(track_b, track_a, tolerance_m=tolerance_m)
            if len(gps["pairs"]) > _MIN_GPS_PAIRS or (source == "tracks" and gps["pairs"]):
                return {
                    "method_used": "gps",
                    "pairs": gps["pairs"],
                    "segments": gps["segments"],
                    "message": None,
                    "pair_count_total": len(gps["pairs"]),
                }
            if source == "tracks":
                return {
                    "method_used": "none",
                    "pairs": [],
                    "segments": [],
                    "message": "GPS-треки есть, но совпадений в tolerance не найдено. Попробуйте Детекции или ручной выбор кадров.",
                    "pair_count_total": 0,
                }
        elif source == "tracks":
            return {
                "method_used": "none",
                "pairs": [],
                "segments": [],
                "message": "GPS-треки отсутствуют. Переключитесь на поиск по детекциям или выберите кадры вручную.",
                "pair_count_total": 0,
            }

    if try_dets:
        dets_b = _load_detections(source_before)
        dets_a = _load_detections(source_after)
        det = sync_by_detections(dets_b, dets_a)
        if det["pairs"]:
            msg = None
            if source == "auto" and try_tracks:
                msg = "GPS-треки недостаточны. Переключено на поиск по детекциям."
            return {
                "method_used": "detections",
                "pairs": det["pairs"],
                "segments": det["segments"],
                "message": msg,
                "pair_count_total": len(det["pairs"]),
            }
        if source == "detections":
            return {
                "method_used": "none",
                "pairs": [],
                "segments": [],
                "message": "Совпадений по детекциям не найдено. Используйте ручной выбор кадров.",
                "pair_count_total": 0,
            }

    return {
        "method_used": "none",
        "pairs": [],
        "segments": [],
        "message": "Совпадений не найдено. Используйте ручной выбор кадров.",
        "pair_count_total": 0,
    }
