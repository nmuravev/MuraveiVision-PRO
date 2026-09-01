"""Greedy IoU tracker — no ByteTrack / lap (air-gap safe)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _iou(a: dict[str, float], b: dict[str, float]) -> float:
    ax1, ay1, ax2, ay2 = a["x1"], a["y1"], a["x2"], a["y2"]
    bx1, by1, bx2, by2 = b["x1"], b["y1"], b["x2"], b["y2"]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _center(b: dict[str, float]) -> tuple[float, float]:
    return ((b["x1"] + b["x2"]) * 0.5, (b["y1"] + b["y2"]) * 0.5)


def _shift(b: dict[str, float], dx: float, dy: float) -> dict[str, float]:
    return {
        "x1": b["x1"] + dx,
        "y1": b["y1"] + dy,
        "x2": b["x2"] + dx,
        "y2": b["y2"] + dy,
    }


@dataclass
class _Track:
    track_id: int
    bbox: dict[str, float]
    class_en: str
    vx: float = 0.0
    vy: float = 0.0
    hits: int = 1
    age: int = 0
    time_since_update: int = 0


@dataclass
class IoUTracker:
    iou_thresh: float = 0.3
    max_age: int = 8
    _next_id: int = 1
    _tracks: list[_Track] = field(default_factory=list)

    def update(
        self,
        detections: list[dict[str, Any]],
        ego_vx: float = 0.0,
        ego_vy: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Assign stable track_id; return detections with track fields."""
        for tr in self._tracks:
            tr.age += 1
            tr.time_since_update += 1
            # Predict: ego + object velocity
            tr.bbox = _shift(tr.bbox, tr.vx + ego_vx, tr.vy + ego_vy)

        unmatched_det = set(range(len(detections)))
        unmatched_trk = set(range(len(self._tracks)))
        pairs: list[tuple[float, int, int]] = []
        for ti, tr in enumerate(self._tracks):
            for di, det in enumerate(detections):
                bbox = det.get("bbox") or {}
                if not bbox:
                    continue
                # Prefer same class when available
                same = str(det.get("class_en") or "") == tr.class_en
                score = _iou(tr.bbox, bbox)
                if same:
                    score += 0.05
                if score >= self.iou_thresh:
                    pairs.append((score, ti, di))
        pairs.sort(reverse=True)

        assigned_trk: set[int] = set()
        assigned_det: set[int] = set()
        matches: list[tuple[int, int]] = []
        for _score, ti, di in pairs:
            if ti in assigned_trk or di in assigned_det:
                continue
            assigned_trk.add(ti)
            assigned_det.add(di)
            matches.append((ti, di))

        unmatched_trk -= assigned_trk
        unmatched_det -= assigned_det

        out: list[dict[str, Any]] = []
        for ti, di in matches:
            tr = self._tracks[ti]
            det = detections[di]
            bbox = dict(det["bbox"])
            cx, cy = _center(bbox)
            pcx, pcy = _center(tr.bbox)
            # Undo prediction for velocity estimate vs previous measured
            raw_vx = cx - (pcx - tr.vx - ego_vx) - ego_vx
            raw_vy = cy - (pcy - tr.vy - ego_vy) - ego_vy
            tr.vx = 0.55 * raw_vx + 0.45 * tr.vx
            tr.vy = 0.55 * raw_vy + 0.45 * tr.vy
            tr.bbox = bbox
            tr.class_en = str(det.get("class_en") or tr.class_en)
            tr.hits += 1
            tr.time_since_update = 0
            enriched = dict(det)
            enriched["track_id"] = tr.track_id
            enriched["id"] = f"trk-{tr.track_id}"
            enriched["motion"] = {
                "vx": round(tr.vx, 5),
                "vy": round(tr.vy, 5),
                "speed": round((tr.vx * tr.vx + tr.vy * tr.vy) ** 0.5, 5),
                "ego_vx": round(ego_vx, 5),
                "ego_vy": round(ego_vy, 5),
            }
            out.append(enriched)

        for di in sorted(unmatched_det):
            det = detections[di]
            bbox = dict(det.get("bbox") or {})
            if not bbox:
                out.append(det)
                continue
            tid = self._next_id
            self._next_id += 1
            self._tracks.append(
                _Track(
                    track_id=tid,
                    bbox=bbox,
                    class_en=str(det.get("class_en") or ""),
                )
            )
            enriched = dict(det)
            enriched["track_id"] = tid
            enriched["id"] = f"trk-{tid}"
            enriched["motion"] = {
                "vx": 0.0,
                "vy": 0.0,
                "speed": 0.0,
                "ego_vx": round(ego_vx, 5),
                "ego_vy": round(ego_vy, 5),
            }
            out.append(enriched)

        # Drop stale tracks
        self._tracks = [t for t in self._tracks if t.time_since_update <= self.max_age]
        return out

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1
