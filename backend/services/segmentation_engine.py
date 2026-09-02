"""Archive-only YOLO26-seg inference.

Detect ≠ Segment: do not import the detect engine or trainer from here,
must not write detections, and must not load YOLOE-seg / SAM2.
"""
from __future__ import annotations

import io
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from services.db import BASE_DIR

IMGSZ = 640
DEFAULT_CONF = 0.25
MAX_POLY_POINTS = 256
SEG_WEIGHT_NAMES = ("yolo26n-seg.pt", "yolo26s-seg.pt")
MODELS_DIR = BASE_DIR / "assets" / "models"

_engine: SegmentationEngine | None = None
_engine_lock = threading.Lock()


def _weight_ok(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 1024
    except OSError:
        return False


def list_available_weights() -> list[str]:
    return [name for name in SEG_WEIGHT_NAMES if _weight_ok(MODELS_DIR / name)]


def resolve_seg_weights() -> Path | None:
    """Prefer nano, then small. Ignore YOLOE-seg and any other *-seg.pt."""
    names = list_available_weights()
    if not names:
        return None
    return MODELS_DIR / names[0]


def resolve_named_weight(name: str) -> Path:
    """Whitelist yolo26n/s-seg under MODELS_DIR. Reject traversal, YOLOE, detect."""
    raw = (name or "").strip()
    if not raw:
        raise ValueError("weight name required")
    if "/" in raw or "\\" in raw or ".." in raw:
        raise ValueError("invalid weight name")
    base = Path(raw).name
    lowered = {n.lower(): n for n in SEG_WEIGHT_NAMES}
    canonical = lowered.get(base.lower())
    if canonical is None or "yoloe" in base.lower():
        raise ValueError("only yolo26n-seg.pt / yolo26s-seg.pt are allowed")
    path = MODELS_DIR / canonical
    if not _weight_ok(path):
        raise FileNotFoundError(f"seg weight missing: {canonical}")
    return path


def _empty_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def _as_1d(value: Any) -> list[float]:
    if value is None:
        return []
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    arr = np.asarray(value, dtype=np.float64).reshape(-1)
    return [float(x) for x in arr]


def _polygon_norm(raw: Any) -> list[list[float]]:
    pts = np.asarray(raw, dtype=np.float64)
    if pts.ndim == 1:
        pts = pts.reshape(-1, 2)
    if pts.ndim != 2 or pts.shape[1] < 2 or pts.shape[0] < 3:
        return []
    if pts.shape[0] > MAX_POLY_POINTS:
        idx = np.linspace(0, pts.shape[0] - 1, MAX_POLY_POINTS, dtype=int)
        pts = pts[idx]
    out: list[list[float]] = []
    for x, y in pts[:, :2]:
        out.append(
            [
                float(min(1.0, max(0.0, x))),
                float(min(1.0, max(0.0, y))),
            ]
        )
    return out if len(out) >= 3 else []


def masks_from_results(results: Any) -> list[dict[str, Any]]:
    """Convert Ultralytics seg Results → {class, conf, polygon_norm[]}."""
    masks: list[dict[str, Any]] = []
    if not results:
        return masks
    result = results[0]
    names = getattr(result, "names", None) or {}
    blob = getattr(result, "masks", None)
    boxes = getattr(result, "boxes", None)
    if blob is None:
        return masks
    xyn = getattr(blob, "xyn", None)
    if xyn is None:
        return masks
    cls_list = _as_1d(getattr(boxes, "cls", None)) if boxes is not None else []
    conf_list = _as_1d(getattr(boxes, "conf", None)) if boxes is not None else []
    for i, poly in enumerate(xyn):
        pts = _polygon_norm(poly)
        if len(pts) < 3:
            continue
        cid = int(cls_list[i]) if i < len(cls_list) else 0
        if isinstance(names, dict):
            label = names.get(cid, names.get(str(cid), str(cid)))
        else:
            label = str(cid)
        conf = float(conf_list[i]) if i < len(conf_list) else 0.0
        masks.append(
            {
                "class": str(label),
                "conf": max(0.0, min(1.0, conf)),
                "polygon_norm": pts,
            }
        )
    return masks


def _load_yolo(path: Path) -> Any:
    from ultralytics import YOLO

    return YOLO(str(path))


class SegmentationEngine:
    """YOLO26-seg in VRAM until explicit unload. Does not auto-load on infer."""

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
            "imgsz": IMGSZ,
        }

    def unload(self) -> None:
        self.unload_model()

    def unload_model(self) -> None:
        with self._lock:
            self._model = None
            self._weight_name = None
        _empty_cache()

    def load_model(self, name: str | None = None) -> Path:
        if name:
            path = resolve_named_weight(name)
        else:
            path = resolve_seg_weights()
            if path is None:
                raise FileNotFoundError("seg weights missing")
        with self._lock:
            if self._model is not None and self._weight_name == path.name:
                return path
            self._model = None
            self._weight_name = None
            _empty_cache()
            self._model = _load_yolo(path)
            self._weight_name = path.name
            return path

    def infer_jpeg(self, jpeg: bytes, confidence: float = DEFAULT_CONF) -> dict[str, Any]:
        if not jpeg:
            raise ValueError("image required")
        conf = float(max(0.05, min(0.99, confidence)))
        try:
            img = Image.open(io.BytesIO(jpeg)).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            raise ValueError("invalid jpeg") from exc
        arr = np.asarray(img)
        with self._lock:
            if self._model is None:
                raise RuntimeError("seg model not loaded")
            started = time.perf_counter()
            results = self._model.predict(
                arr,
                imgsz=IMGSZ,
                conf=conf,
                verbose=False,
            )
            masks = masks_from_results(results)
            ms = int((time.perf_counter() - started) * 1000)
            return {
                "masks": masks,
                "weight": self._weight_name,
                "ms": ms,
                "imgsz": IMGSZ,
            }


def get_seg_engine() -> SegmentationEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = SegmentationEngine()
        return _engine
