"""Detection crop JPEG as base64 for vision LLM (file or video frame fallback)."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]

from services.db import CROPS_DIR, get_detection
from services.security import assert_in_archive


def _read_file_b64(path: Path) -> str | None:
    if not path.is_file():
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _crop_from_video(row: dict[str, Any]) -> str | None:
    source = str(row.get("source_video") or "").strip()
    if not source:
        return None
    try:
        from services.batch_scanner import _resolve_video

        video_abs, _ = _resolve_video(source)
    except (FileNotFoundError, ValueError, RuntimeError):
        return None

    import cv2

    cap = cv2.VideoCapture(str(video_abs))
    if not cap.isOpened():
        return None
    t = float(row.get("time_sec") or 0)
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None

    fh, fw = frame.shape[:2]
    x = float(row.get("bbox_x") or 0)
    y = float(row.get("bbox_y") or 0)
    bw = float(row.get("bbox_w") or 0.05)
    bh = float(row.get("bbox_h") or 0.05)
    if max(x, y, bw, bh) <= 1.5:
        x1 = max(0, min(fw - 1, int(x * fw)))
        y1 = max(0, min(fh - 1, int(y * fh)))
        x2 = max(x1 + 1, min(fw, int((x + bw) * fw)))
        y2 = max(y1 + 1, min(fh, int((y + bh) * fh)))
    else:
        x1 = max(0, min(fw - 1, int(x)))
        y1 = max(0, min(fh - 1, int(y)))
        x2 = max(x1 + 1, min(fw, int(x + bw)))
        y2 = max(y1 + 1, min(fh, int(y + bh)))

    patch = frame[y1:y2, x1:x2]
    if patch.size == 0:
        return None
    encoded, buf = cv2.imencode(".jpg", patch, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not encoded:
        return None
    return base64.b64encode(buf.tobytes()).decode("ascii")


def detection_crop_b64(detection_id: str) -> str | None:
    """Load crop JPEG for a detection: file on disk, else extract from source video."""
    row = get_detection(detection_id)
    if not row or row.get("is_deleted"):
        return None

    candidates: list[Path] = []
    crop = row.get("crop_path")
    if crop:
        raw = str(crop)
        try:
            candidates.append(assert_in_archive(raw))
        except Exception:  # noqa: BLE001
            p = Path(raw)
            if p.is_file():
                candidates.append(p)
        if not raw.startswith("archive"):
            candidates.append(BASE_DIR / raw.replace("\\", "/").lstrip("/"))

    candidates.append(CROPS_DIR / f"{detection_id}.jpg")
    candidates.append(BASE_DIR / "archive" / "crops" / f"{detection_id}.jpg")

    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        data = _read_file_b64(path)
        if data:
            return data

    return _crop_from_video(row)


def video_frame_b64(source_video: str, time_sec: float) -> str | None:
    """Full video frame at time_sec as JPEG base64."""
    try:
        from services.batch_scanner import _resolve_video

        video_abs, _ = _resolve_video(source_video)
    except (FileNotFoundError, ValueError, RuntimeError):
        return None

    import cv2

    cap = cv2.VideoCapture(str(video_abs))
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, float(time_sec)) * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        encoded, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if not encoded:
            return None
        return base64.b64encode(buf.tobytes()).decode("ascii")
    finally:
        cap.release()
