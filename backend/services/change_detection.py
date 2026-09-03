"""P3.15 v1: Compare Sync change detection — GPS matching + ORB/diff fallback."""
from __future__ import annotations

import base64
import math
from typing import Any

import cv2
import numpy as np

_EARTH_R_M = 6_371_000.0
_LOW_INLIER = 0.25
_MIN_GPS_COVERAGE = 0.30
_MAX_FRAME_SIDE = 1280


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_R_M * math.asin(min(1.0, math.sqrt(a)))


def _has_gps(det: dict[str, Any]) -> bool:
    lat = det.get("gps_lat")
    lon = det.get("gps_lon")
    if lat is None or lon is None:
        return False
    try:
        return not (float(lat) == 0.0 and float(lon) == 0.0)
    except (TypeError, ValueError):
        return False


def bbox_xyxy(det: dict[str, Any]) -> dict[str, float]:
    x = float(det.get("bbox_x") or 0)
    y = float(det.get("bbox_y") or 0)
    w = float(det.get("bbox_w") or 0)
    h = float(det.get("bbox_h") or 0)
    return {"x1": x, "y1": y, "x2": x + w, "y2": y + h}


def filter_detections_at_time(
    dets: list[dict[str, Any]],
    time_sec: float,
    window_sec: float,
) -> list[dict[str, Any]]:
    t = float(time_sec)
    w = max(0.0, float(window_sec))
    out: list[dict[str, Any]] = []
    for d in dets:
        try:
            ts = float(d.get("time_sec") or 0)
        except (TypeError, ValueError):
            continue
        if abs(ts - t) <= w:
            out.append(d)
    return out


def _det_summary_item(det: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": det["id"],
        "class_name": det.get("class_name"),
        "bbox": bbox_xyxy(det),
        "confidence": det.get("confidence"),
    }
    if _has_gps(det):
        item["gps_lat"] = det.get("gps_lat")
        item["gps_lon"] = det.get("gps_lon")
    return item


def align_by_gps(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    *,
    tolerance_m: float = 10.0,
    moved_m: float = 3.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    before_gps = [d for d in before if _has_gps(d)]
    after_gps = [d for d in after if _has_gps(d)]

    candidates: list[tuple[float, int, int, dict[str, Any], dict[str, Any]]] = []
    for ai, a in enumerate(after_gps):
        for bi, b in enumerate(before_gps):
            if a.get("class_name") != b.get("class_name"):
                continue
            dist = haversine_m(
                float(b["gps_lat"]),
                float(b["gps_lon"]),
                float(a["gps_lat"]),
                float(a["gps_lon"]),
            )
            if dist <= tolerance_m:
                candidates.append((dist, bi, ai, b, a))

    candidates.sort(key=lambda row: row[0])

    matched_before: set[int] = set()
    matched_after: set[int] = set()
    matches: list[dict[str, Any]] = []

    for dist, bi, ai, b, a in candidates:
        if bi in matched_before or ai in matched_after:
            continue
        matched_before.add(bi)
        matched_after.add(ai)
        status = "stable" if dist < moved_m else "moved"
        matches.append(
            {
                "before_id": b["id"],
                "after_id": a["id"],
                "class_name": a.get("class_name"),
                "distance_m": round(dist, 2),
                "status": status,
                "before_bbox": bbox_xyxy(b),
                "after_bbox": bbox_xyxy(a),
            }
        )

    new = [_det_summary_item(a) for i, a in enumerate(after_gps) if i not in matched_after]
    removed = [_det_summary_item(b) for i, b in enumerate(before_gps) if i not in matched_before]
    return matches, new, removed


def _downscale_bgr(frame: np.ndarray, max_side: int = _MAX_FRAME_SIDE) -> tuple[np.ndarray, float]:
    h, w = frame.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return frame, 1.0
    scale = max_side / longest
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA), scale


def extract_video_frame(source_video: str, time_sec: float) -> np.ndarray | None:
    from services.batch_scanner import _resolve_video

    video_abs, _ = _resolve_video(source_video)
    cap = cv2.VideoCapture(str(video_abs))
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(time_sec)) * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        frame, _ = _downscale_bgr(frame)
        return frame
    finally:
        cap.release()


class ChangeDetectionEngine:
    """Stateless ORB matcher reused across calls."""

    def __init__(self) -> None:
        self._orb = cv2.ORB_create(nfeatures=2000)
        self._bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    def align_by_features(
        self,
        img_before: np.ndarray,
        img_after: np.ndarray,
    ) -> tuple[np.ndarray | None, float]:
        gray1 = cv2.cvtColor(img_before, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img_after, cv2.COLOR_BGR2GRAY)
        kp1, des1 = self._orb.detectAndCompute(gray1, None)
        kp2, des2 = self._orb.detectAndCompute(gray2, None)
        if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
            return None, 0.0

        raw = self._bf.knnMatch(des1, des2, k=2)
        good: list[cv2.DMatch] = []
        for pair in raw:
            if len(pair) < 2:
                continue
            m, n = pair
            if m.distance < 0.75 * n.distance:
                good.append(m)
        if len(good) < 4:
            return None, 0.0

        src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if H is None:
            return None, 0.0
        inlier_ratio = float(mask.sum()) / len(good) if mask is not None else 0.0
        return H, inlier_ratio

    def compute_diff_mask(
        self,
        img_before: np.ndarray,
        img_after: np.ndarray,
        H: np.ndarray | None = None,
        *,
        threshold: int = 30,
    ) -> dict[str, Any]:
        g1 = cv2.cvtColor(img_before, cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(img_after, cv2.COLOR_BGR2GRAY)
        h, w = g1.shape[:2]
        if H is not None:
            g2 = cv2.warpPerspective(g2, H, (w, h))

        diff = cv2.absdiff(g1, g2)
        _, mask = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_area = w * h * 0.0005
        regions: list[dict[str, Any]] = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            roi_b = g1[y : y + bh, x : x + bw]
            roi_a = g2[y : y + bh, x : x + bw]
            mb = float(roi_b.mean()) if roi_b.size else 0.0
            ma = float(roi_a.mean()) if roi_a.size else 0.0
            kind = "new" if ma > mb + 5 else "removed"
            regions.append(
                {
                    "kind": kind,
                    "bbox": {
                        "x1": x / w,
                        "y1": y / h,
                        "x2": (x + bw) / w,
                        "y2": (y + bh) / h,
                    },
                }
            )

        diff_blurred = cv2.GaussianBlur(diff, (21, 21), 0)
        heatmap_norm = cv2.normalize(diff_blurred, None, 0, 255, cv2.NORM_MINMAX)
        heatmap_u8 = np.asarray(heatmap_norm, dtype=np.uint8)
        heatmap_color = cv2.applyColorMap(heatmap_u8, cv2.COLORMAP_JET)
        ok, png_buf = cv2.imencode(".png", heatmap_color)
        heatmap_b64 = base64.b64encode(png_buf.tobytes()).decode("ascii") if ok else ""

        return {"regions": regions, "heatmap_b64": heatmap_b64}


_engine: ChangeDetectionEngine | None = None


def get_change_engine() -> ChangeDetectionEngine:
    global _engine
    if _engine is None:
        _engine = ChangeDetectionEngine()
    return _engine


def _gps_coverage(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> float:
    if not before or not after:
        return 0.0
    b_ratio = sum(1 for d in before if _has_gps(d)) / len(before)
    a_ratio = sum(1 for d in after if _has_gps(d)) / len(after)
    return min(b_ratio, a_ratio)


def _build_summary(
    total_before: int,
    total_after: int,
    matches: list[dict[str, Any]],
    new: list[dict[str, Any]],
    removed: list[dict[str, Any]],
) -> dict[str, int]:
    moved = sum(1 for m in matches if m.get("status") == "moved")
    matched = len(matches)
    stable = matched - moved
    return {
        "total_before": total_before,
        "total_after": total_after,
        "matched": matched,
        "stable": stable,
        "moved": moved,
        "new": len(new),
        "removed": len(removed),
    }


def analyze_pair(
    *,
    video_before: str,
    video_after: str,
    time_before: float,
    time_after: float,
    tolerance_m: float = 10.0,
    moved_m: float = 3.0,
    time_window_sec: float = 0.5,
    use_gps: bool = True,
    use_image_fallback: bool = True,
) -> dict[str, Any]:
    from services.batch_scanner import _resolve_video
    from services.db import list_detections

    _, source_before = _resolve_video(video_before)
    _, source_after = _resolve_video(video_after)

    # KEEP: session trace — do not remove without explicit user order
    from services.trace_middleware import pipeline_trace

    pipeline_trace(
        "cd",
        f"analyze_pair before={source_before}@{time_before:.1f} after={source_after}@{time_after:.1f}",
    )

    before_all = list_detections(source_video=source_before)
    after_all = list_detections(source_video=source_after)
    before_at = filter_detections_at_time(before_all, time_before, time_window_sec)
    after_at = filter_detections_at_time(after_all, time_after, time_window_sec)

    coverage = _gps_coverage(before_at, after_at)
    matches: list[dict[str, Any]] = []
    new: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    method = "none"
    aligned = False
    message: str | None = None
    image_diff: dict[str, Any] | None = None

    run_gps = use_gps and coverage >= _MIN_GPS_COVERAGE
    if run_gps:
        matches, new, removed = align_by_gps(
            before_at,
            after_at,
            tolerance_m=tolerance_m,
            moved_m=moved_m,
        )
        method = "gps"
        aligned = True

    need_image = use_image_fallback and (not run_gps or coverage < _MIN_GPS_COVERAGE)
    if need_image:
        frame_before = extract_video_frame(video_before, time_before)
        frame_after = extract_video_frame(video_after, time_after)
        if frame_before is None or frame_after is None:
            if not run_gps:
                message = "Не удалось извлечь кадры для сравнения"
        else:
            engine = get_change_engine()
            H, inlier_ratio = engine.align_by_features(frame_before, frame_after)
            img_aligned = H is not None and inlier_ratio >= _LOW_INLIER
            diff_out = engine.compute_diff_mask(
                frame_before, frame_after, H if img_aligned else None
            )
            image_diff = {
                "inlier_ratio": round(inlier_ratio, 3),
                "regions": diff_out["regions"],
                "heatmap_b64": diff_out.get("heatmap_b64") or None,
            }
            if img_aligned:
                aligned = True
                method = "hybrid" if run_gps else "image"
            else:
                if not run_gps:
                    message = "Выравнивание кадров не удалось (низкий inlier_ratio)"
                elif not message:
                    message = "ORB fallback: выравнивание слабое, показан только GPS-результат"

    summary = _build_summary(len(before_at), len(after_at), matches, new, removed)

    return {
        "method": method,
        "aligned": aligned,
        "message": message,
        "summary": summary,
        "matches": matches,
        "new": new,
        "removed": removed,
        "image_diff": image_diff,
    }
