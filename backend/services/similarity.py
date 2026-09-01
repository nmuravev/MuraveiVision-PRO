"""Find-similar: class filter + visual embedding (air-gap safe).

Uses local perceptual features (HSV histogram + edge energy). OpenAI CLIP
weights are not shipped; MobileCLIP TS is YOLOE-text specific — we do not
download models. Label this method as `hist+class` in API responses.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from main import BASE_DIR
from services.db import get_detection, list_detections

CROPS_DIR = BASE_DIR / "archive" / "crops"
_EMBED_CACHE: dict[str, tuple[float, np.ndarray]] = {}


def _resolve_crop(row: dict[str, Any]) -> Path | None:
    crop = row.get("crop_path")
    if crop:
        path = Path(str(crop))
        if not path.is_absolute():
            path = BASE_DIR / path
        if path.exists() and path.stat().st_size > 32:
            return path
    det_id = str(row.get("id") or "")
    if det_id:
        fallback = CROPS_DIR / f"{det_id}.jpg"
        if fallback.exists() and fallback.stat().st_size > 32:
            return fallback
    return None


def embed_image(path: Path) -> np.ndarray:
    """Compact visual signature — no network, works offline."""
    key = str(path.resolve())
    mtime = path.stat().st_mtime
    cached = _EMBED_CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1]

    from PIL import Image

    img = Image.open(path).convert("RGB").resize((96, 96))
    arr = np.asarray(img, dtype=np.float32) / 255.0
    # RGB coarse hist
    parts: list[np.ndarray] = []
    for ch in range(3):
        hist, _ = np.histogram(arr[:, :, ch], bins=16, range=(0.0, 1.0), density=True)
        parts.append(hist.astype(np.float32))
    # Simple gradient magnitude energy map
    gray = arr.mean(axis=2)
    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))
    parts.append(np.array([gx.mean(), gy.mean(), gray.std(), gray.mean()], dtype=np.float32))
    vec = np.concatenate(parts)
    norm = float(np.linalg.norm(vec)) or 1.0
    vec = vec / norm
    _EMBED_CACHE[key] = (mtime, vec)
    if len(_EMBED_CACHE) > 4000:
        # drop arbitrary oldest-ish entries
        for k in list(_EMBED_CACHE.keys())[:500]:
            _EMBED_CACHE.pop(k, None)
    return vec


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def find_similar(detection_id: str, top_k: int = 12, same_class: bool = True) -> dict[str, Any]:
    probe = get_detection(detection_id)
    if probe is None or probe.get("is_deleted"):
        raise ValueError("detection not found")
    crop = _resolve_crop(probe)
    if crop is None:
        raise ValueError("detection has no crop")

    probe_vec = embed_image(crop)
    class_name = str(probe.get("class_name") or "")
    candidates = list_detections(include_deleted=False)
    scored: list[dict[str, Any]] = []
    for row in candidates:
        if str(row["id"]) == detection_id:
            continue
        if same_class and class_name and str(row.get("class_name")) != class_name:
            continue
        other_crop = _resolve_crop(row)
        if other_crop is None:
            continue
        try:
            sim = cosine(probe_vec, embed_image(other_crop))
        except Exception:  # noqa: BLE001
            continue
        scored.append(
            {
                "id": row["id"],
                "class_name": row["class_name"],
                "class_id": row["class_id"],
                "source_video": row["source_video"],
                "time_sec": row["time_sec"],
                "confidence": row["confidence"],
                "crop_path": row.get("crop_path"),
                "similarity": round(sim, 4),
            }
        )
    scored.sort(key=lambda r: float(r["similarity"]), reverse=True)
    top_k = max(1, min(50, int(top_k)))
    return {
        "query_id": detection_id,
        "class_name": class_name,
        "method": "hist+class",
        "same_class": same_class,
        "results": scored[:top_k],
    }
