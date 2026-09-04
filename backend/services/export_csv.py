"""CSV export for persisted detections (HQ tabular reports)."""
from __future__ import annotations

import csv
import io
from typing import Any

from services.db import list_detections

# Stored bbox is normalized xywh in [0,1] (see db.save_crop_jpeg / insert).
CSV_COORD_COMMENT = "# Coordinates normalized [0-1] (x1,y1,x2,y2 from bbox_x/y/w/h)"
CSV_HEADER = [
    "time_sec",
    "class_name",
    "confidence",
    "x1",
    "y1",
    "x2",
    "y2",
    "gps_lat",
    "gps_lon",
]


def _bbox_xyxy(row: dict[str, Any]) -> tuple[float, float, float, float]:
    x = float(row.get("bbox_x") or 0.0)
    y = float(row.get("bbox_y") or 0.0)
    w = float(row.get("bbox_w") or 0.0)
    h = float(row.get("bbox_h") or 0.0)
    return (x, y, x + w, y + h)


def generate_detections_csv(source_video: str) -> str:
    """Build CSV text for all non-deleted detections of one video."""
    rows = list_detections(source_video, include_deleted=False)
    buf = io.StringIO()
    buf.write(CSV_COORD_COMMENT + "\n")
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADER)
    for row in rows:
        x1, y1, x2, y2 = _bbox_xyxy(row)
        writer.writerow(
            [
                row.get("time_sec"),
                row.get("class_name") or "",
                row.get("confidence"),
                f"{x1:.6f}",
                f"{y1:.6f}",
                f"{x2:.6f}",
                f"{y2:.6f}",
                "" if row.get("gps_lat") is None else row.get("gps_lat"),
                "" if row.get("gps_lon") is None else row.get("gps_lon"),
            ]
        )
    return buf.getvalue()
