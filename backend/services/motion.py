"""Ego-motion (camera) + relative object motion — OpenCV, CPU-friendly."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class MotionState:
    prev_gray: np.ndarray | None = None
    ego_vx: float = 0.0
    ego_vy: float = 0.0
    frame_w: int = 0
    frame_h: int = 0


def _to_gray_small(rgb: np.ndarray, max_w: int = 320) -> tuple[np.ndarray, float]:
    """Downscale RGB→gray for LK; returns (gray, scale_to_full)."""
    import cv2

    h, w = rgb.shape[:2]
    scale = 1.0
    if w > max_w:
        scale = max_w / float(w)
        nh = max(32, int(h * scale))
        nw = max(32, int(w * scale))
        small = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
    else:
        small = rgb
    if small.ndim == 3:
        gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    else:
        gray = small
    return gray, (1.0 / scale) if scale > 0 else 1.0


def estimate_ego(state: MotionState, rgb: np.ndarray) -> tuple[float, float]:
    """Median sparse LK displacement of background features (normalized 0..1 coords)."""
    import cv2

    h, w = rgb.shape[:2]
    state.frame_w, state.frame_h = w, h
    gray, to_full = _to_gray_small(rgb)
    if state.prev_gray is None or state.prev_gray.shape != gray.shape:
        state.prev_gray = gray
        state.ego_vx = 0.0
        state.ego_vy = 0.0
        return 0.0, 0.0

    pts = cv2.goodFeaturesToTrack(
        state.prev_gray,
        maxCorners=64,
        qualityLevel=0.01,
        minDistance=8,
        blockSize=7,
    )
    if pts is None or len(pts) < 6:
        state.prev_gray = gray
        return state.ego_vx, state.ego_vy

    nxt, st, _err = cv2.calcOpticalFlowPyrLK(
        state.prev_gray,
        gray,
        pts,
        None,
        winSize=(21, 21),
        maxLevel=2,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
    )
    state.prev_gray = gray
    if nxt is None or st is None:
        return state.ego_vx, state.ego_vy

    good_old = pts[st.flatten() == 1]
    good_new = nxt[st.flatten() == 1]
    if len(good_old) < 4:
        return state.ego_vx, state.ego_vy

    dxy = (good_new - good_old).reshape(-1, 2)
    # pixels on small image → full-frame pixels → normalized
    med = np.median(dxy, axis=0)
    dx_px = float(med[0]) * to_full
    dy_px = float(med[1]) * to_full
    ego_vx = dx_px / max(1.0, float(w))
    ego_vy = dy_px / max(1.0, float(h))
    # EMA smooth
    state.ego_vx = 0.65 * state.ego_vx + 0.35 * ego_vx
    state.ego_vy = 0.65 * state.ego_vy + 0.35 * ego_vy
    return state.ego_vx, state.ego_vy


def attach_motion(
    objects: list[dict[str, Any]],
    prev_centers: dict[str, tuple[float, float]],
    ego_vx: float,
    ego_vy: float,
    alpha: float = 0.45,
) -> tuple[list[dict[str, Any]], dict[str, tuple[float, float]]]:
    """Fill motion {vx,vy,speed,ego_*} using center deltas minus ego (normalized)."""
    next_centers: dict[str, tuple[float, float]] = {}
    out: list[dict[str, Any]] = []
    for obj in objects:
        bbox = obj.get("bbox") or {}
        cx = (float(bbox.get("x1", 0)) + float(bbox.get("x2", 0))) * 0.5
        cy = (float(bbox.get("y1", 0)) + float(bbox.get("y2", 0))) * 0.5
        key = str(obj.get("track_id") or obj.get("id") or "")
        next_centers[key] = (cx, cy)
        prev = prev_centers.get(key)
        if prev is None:
            vx = vy = 0.0
        else:
            raw_vx = cx - prev[0] - ego_vx
            raw_vy = cy - prev[1] - ego_vy
            old = obj.get("motion") or {}
            ovx = float(old.get("vx") or 0.0)
            ovy = float(old.get("vy") or 0.0)
            vx = alpha * raw_vx + (1.0 - alpha) * ovx
            vy = alpha * raw_vy + (1.0 - alpha) * ovy
        speed = float((vx * vx + vy * vy) ** 0.5)
        enriched = dict(obj)
        enriched["motion"] = {
            "vx": round(vx, 5),
            "vy": round(vy, 5),
            "speed": round(speed, 5),
            "ego_vx": round(ego_vx, 5),
            "ego_vy": round(ego_vy, 5),
        }
        out.append(enriched)
    return out, next_centers
