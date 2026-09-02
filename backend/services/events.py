"""Unified event timeline: local detections + incoming network targets."""
from __future__ import annotations

import time
from typing import Any

from services.db import list_recent_detections
from services.network import list_recent_incoming_targets


def _clamp_window(window: float) -> float:
    return max(10.0, min(float(window), 86400.0))


def _clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), 200))


def list_timeline(*, window: float = 300.0, limit: int = 100) -> list[dict[str, Any]]:
    """Merge recent local detections and incoming network targets, newest first."""
    win = _clamp_window(window)
    lim = _clamp_limit(limit)
    since = time.time() - win
    events: list[dict[str, Any]] = []
    for row in list_recent_detections(since, lim):
        events.append(
            {
                "id": row["id"],
                "type": "local_detection",
                "time_sec": float(row.get("time_sec") or 0),
                "class_name": str(row.get("class_name") or ""),
                "confidence": float(row.get("confidence") or 0),
                "source_video": row.get("source_video"),
                "source_base": None,
                "created_at": float(row.get("created_at") or 0),
                "gps_lat": row.get("gps_lat"),
                "gps_lon": row.get("gps_lon"),
                "notes": row.get("user_notes") or None,
            }
        )
    for row in list_recent_incoming_targets(since, lim):
        events.append(
            {
                "id": row["id"],
                "type": "network_target",
                "time_sec": None,
                "class_name": str(row.get("class_name") or ""),
                "confidence": float(row.get("confidence") or 0),
                "source_video": row.get("source_video"),
                "source_base": row.get("source_base"),
                "created_at": float(row.get("created_at") or 0),
                "gps_lat": row.get("gps_lat"),
                "gps_lon": row.get("gps_lon"),
                "notes": row.get("notes"),
            }
        )
    events.sort(key=lambda e: float(e.get("created_at") or 0), reverse=True)
    return events[:lim]
