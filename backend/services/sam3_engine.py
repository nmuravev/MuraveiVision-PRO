"""P3.13.3a: archive-only SAM3 interactive refine (Ultralytics SAM).

Detect ≠ YOLO-seg ≠ SAM3. Does not write detections/train.
Uses: from ultralytics import SAM; SAM(\"sam3.pt\")
"""
from __future__ import annotations

import io
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from services.db import BASE_DIR

MODELS_DIR = BASE_DIR / "assets" / "models"
SAM3_WEIGHT_NAMES = ("sam3.pt",)
MAX_POLY_POINTS = 256

_engine: Sam3Engine | None = None
_engine_lock = threading.Lock()


def _weight_ok(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 1024
    except OSError:
        return False


def list_available_weights() -> list[str]:
    return [name for name in SAM3_WEIGHT_NAMES if _weight_ok(MODELS_DIR / name)]


def resolve_named_weight(name: str | None = None) -> Path:
    raw = (name or "").strip() or SAM3_WEIGHT_NAMES[0]
    if "/" in raw or "\\" in raw or ".." in raw:
        raise ValueError("invalid weight name")
    base = Path(raw).name
    lowered = {n.lower(): n for n in SAM3_WEIGHT_NAMES}
    canonical = lowered.get(base.lower())
    if canonical is None:
        raise ValueError("only sam3.pt is allowed")
    path = MODELS_DIR / canonical
    if not _weight_ok(path):
        raise FileNotFoundError(f"SAM3 weight missing: {canonical}")
    return path


def _empty_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def mask_to_polygon_norm(mask: np.ndarray) -> list[list[float]]:
    """Binary HxW → contour points normalized to [0,1]. Empty if no usable contour."""
    arr = np.asarray(mask)
    if arr.ndim == 3:
        arr = arr.squeeze()
    if arr.ndim != 2 or arr.size == 0:
        return []
    h, w = int(arr.shape[0]), int(arr.shape[1])
    if h < 1 or w < 1:
        return []
    binary = (arr > 0.5).astype(np.uint8) * 255 if arr.dtype != np.uint8 else arr
    if binary.max() == 1:
        binary = binary * 255
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return []
    cnt = max(contours, key=cv2.contourArea)
    if cv2.contourArea(cnt) < 4:
        return []
    pts = cnt.reshape(-1, 2).astype(np.float64)
    if pts.shape[0] > MAX_POLY_POINTS:
        idx = np.linspace(0, pts.shape[0] - 1, MAX_POLY_POINTS, dtype=int)
        pts = pts[idx]
    out: list[list[float]] = []
    for x, y in pts:
        out.append(
            [
                float(min(1.0, max(0.0, x / float(w)))),
                float(min(1.0, max(0.0, y / float(h)))),
            ]
        )
    return out if len(out) >= 3 else []


def _unload_yolo_seg() -> None:
    try:
        from services.segmentation_engine import get_seg_engine

        get_seg_engine().unload_model()
    except Exception:  # noqa: BLE001
        pass


def _load_sam(path: Path) -> Any:
    from ultralytics import SAM

    return SAM(str(path))


def _masks_from_sam_results(results: Any, h: int, w: int) -> list[dict[str, Any]]:
    masks_out: list[dict[str, Any]] = []
    if not results:
        return masks_out
    result = results[0]
    blob = getattr(result, "masks", None)
    if blob is None:
        return masks_out

    # Prefer normalized polygons when Ultralytics provides them
    xyn = getattr(blob, "xyn", None)
    if xyn is not None:
        for poly in xyn:
            pts = np.asarray(poly, dtype=np.float64)
            if pts.ndim == 1:
                pts = pts.reshape(-1, 2)
            if pts.ndim != 2 or pts.shape[0] < 3:
                continue
            if pts.shape[0] > MAX_POLY_POINTS:
                idx = np.linspace(0, pts.shape[0] - 1, MAX_POLY_POINTS, dtype=int)
                pts = pts[idx]
            polygon = [
                [float(min(1.0, max(0.0, float(x)))), float(min(1.0, max(0.0, float(y))))]
                for x, y in pts[:, :2]
            ]
            if len(polygon) >= 3:
                masks_out.append({"class": "object", "conf": 1.0, "polygon_norm": polygon})
        if masks_out:
            return masks_out

    data = getattr(blob, "data", None)
    if data is None:
        return masks_out
    if hasattr(data, "cpu"):
        data = data.cpu().numpy()
    arr = np.asarray(data)
    if arr.ndim == 2:
        arr = arr[None, ...]
    for i in range(arr.shape[0]):
        poly = mask_to_polygon_norm(arr[i])
        if len(poly) >= 3:
            masks_out.append({"class": "object", "conf": 1.0, "polygon_norm": poly})
    return masks_out


class Sam3Engine:
    """SAM3 in VRAM until explicit unload. Mutual exclusion with YOLO-seg."""

    def __init__(self) -> None:
        self._model: Any = None
        self._weight_name: str | None = None
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        available = list_available_weights()
        return {
            "ready": bool(available),
            "loaded": self._model is not None,
            "weight": self._weight_name or (available[0] if available else None),
            "available": available,
        }

    def unload_model(self) -> None:
        with self._lock:
            self._model = None
            self._weight_name = None
        _empty_cache()

    def load_model(self, name: str | None = None) -> Path:
        path = resolve_named_weight(name)
        _unload_yolo_seg()
        with self._lock:
            if self._model is not None and self._weight_name == path.name:
                return path
            self._model = None
            self._weight_name = None
            _empty_cache()
            self._model = _load_sam(path)
            self._weight_name = path.name
            return path

    def infer_prompts(
        self,
        jpeg: bytes,
        *,
        points_norm: list[dict[str, Any]] | None = None,
        bboxes_norm: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not jpeg:
            raise ValueError("image required")
        points_norm = points_norm or []
        bboxes_norm = bboxes_norm or []
        if not points_norm and not bboxes_norm:
            raise ValueError("points or bboxes required")

        try:
            img = Image.open(io.BytesIO(jpeg)).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            raise ValueError("invalid jpeg") from exc
        arr = np.asarray(img)
        h, w = int(arr.shape[0]), int(arr.shape[1])
        if h < 1 or w < 1:
            raise ValueError("invalid image size")

        kwargs: dict[str, Any] = {"verbose": False}
        if points_norm:
            pts: list[list[float]] = []
            labels: list[int] = []
            for p in points_norm:
                x = float(p.get("x", 0.0))
                y = float(p.get("y", 0.0))
                lab = int(p.get("label", 1))
                pts.append([x * w, y * h])
                labels.append(1 if lab >= 1 else 0)
            kwargs["points"] = pts
            kwargs["labels"] = labels
        if bboxes_norm:
            boxes: list[list[float]] = []
            for b in bboxes_norm:
                x1 = float(b.get("x1", 0.0)) * w
                y1 = float(b.get("y1", 0.0)) * h
                x2 = float(b.get("x2", 0.0)) * w
                y2 = float(b.get("y2", 0.0)) * h
                boxes.append([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)])
            kwargs["bboxes"] = boxes

        with self._lock:
            if self._model is None:
                raise RuntimeError("SAM3 model not loaded")
            started = time.perf_counter()
            results = self._model(arr, **kwargs)
            masks = _masks_from_sam_results(results, h, w)
            ms = int((time.perf_counter() - started) * 1000)
            return {
                "masks": masks,
                "weight": self._weight_name,
                "ms": ms,
            }


def get_sam3_engine() -> Sam3Engine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = Sam3Engine()
        return _engine
