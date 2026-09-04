"""Find-similar: class filter + visual embedding (air-gap safe).

Preferred image encoder is CLIP ``encode_image`` when the ``clip`` package is
installed **and** ViT-B/32 weights are already cached locally. We never download
weights on the field machine.

``mobileclip2_b.ts`` is a YOLOE **text** encoder — it is not used here.

Fallback method is labelled ``hist+class`` (HSV histogram + edge energy).
CLIP and hist vectors are never mixed in one ranking.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np

from services.db import (
    BASE_DIR,
    get_detection,
    get_embedding,
    list_detections,
    upsert_embedding,
)

CROPS_DIR = BASE_DIR / "archive" / "crops"
METHOD_CLIP = "clip"
METHOD_HIST = "hist+class"
CANDIDATE_LIMIT = 2000
_CLIP_WEIGHTS = Path.home() / ".cache" / "clip" / "ViT-B-32.pt"

_EMBED_CACHE: dict[str, tuple[float, np.ndarray]] = {}
_clip_model: Any = None
_clip_preprocess: Any = None
_clip_device: str = "cpu"
_clip_failed = False

# Tests may replace this to force a method or inject a fake embedder.
_force_method: str | None = None
_embed_hook: Callable[[Path, str], np.ndarray] | None = None


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


def clip_available() -> bool:
    """True when CLIP image encoder can load without a network fetch."""
    if _clip_failed:
        return False
    try:
        import clip  # noqa: F401
    except ImportError:
        return False
    return _CLIP_WEIGHTS.is_file() and _CLIP_WEIGHTS.stat().st_size > 1024


def active_method() -> str:
    if _force_method in {METHOD_CLIP, METHOD_HIST}:
        return _force_method
    return METHOD_CLIP if clip_available() else METHOD_HIST


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
    parts: list[np.ndarray] = []
    for ch in range(3):
        hist, _ = np.histogram(arr[:, :, ch], bins=16, range=(0.0, 1.0), density=True)
        parts.append(hist.astype(np.float32))
    gray = arr.mean(axis=2)
    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))
    parts.append(np.array([gx.mean(), gy.mean(), gray.std(), gray.mean()], dtype=np.float32))
    vec = np.concatenate(parts)
    norm = float(np.linalg.norm(vec)) or 1.0
    vec = vec / norm
    _EMBED_CACHE[key] = (mtime, vec)
    if len(_EMBED_CACHE) > 4000:
        for k in list(_EMBED_CACHE.keys())[:500]:
            _EMBED_CACHE.pop(k, None)
    return vec


def _get_clip() -> tuple[Any, Any] | tuple[None, None]:
    global _clip_model, _clip_preprocess, _clip_device, _clip_failed
    if _clip_model is not None:
        return _clip_model, _clip_preprocess
    if not clip_available():
        return None, None
    try:
        import clip
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model, preprocess = clip.load("ViT-B/32", device=device, jit=False)
        model.eval()
        _clip_model = model
        _clip_preprocess = preprocess
        _clip_device = device
        return model, preprocess
    except Exception:  # noqa: BLE001
        _clip_failed = True
        return None, None


def embed_clip(path: Path) -> np.ndarray | None:
    model, preprocess = _get_clip()
    if model is None or preprocess is None:
        return None
    from PIL import Image
    import torch

    img = preprocess(Image.open(path).convert("RGB")).unsqueeze(0)
    img = img.to(_clip_device)
    with torch.no_grad():
        feat = model.encode_image(img)
    vec = feat.float().cpu().numpy().reshape(-1).astype(np.float32)
    norm = float(np.linalg.norm(vec)) or 1.0
    return vec / norm


def _vec_from_blob(blob: bytes) -> np.ndarray | None:
    if not blob:
        return None
    vec = np.frombuffer(blob, dtype=np.float32)
    if vec.size == 0:
        return None
    return np.array(vec, dtype=np.float32, copy=True)


def embed_for_row(row: dict[str, Any], *, method: str | None = None) -> tuple[np.ndarray, str] | None:
    """Return (L2 vector, method) using SQLite cache keyed by detection_id + mtime."""
    crop = _resolve_crop(row)
    if crop is None:
        return None
    want = method or active_method()
    mtime = float(crop.stat().st_mtime)
    det_id = str(row.get("id") or "")
    if det_id:
        cached = get_embedding(det_id)
        if (
            cached
            and cached.get("method") == want
            and abs(float(cached.get("crop_mtime") or 0) - mtime) < 1e-3
        ):
            vec = _vec_from_blob(cached.get("embedding") or b"")
            if vec is not None and vec.size > 0:
                return vec, want

    try:
        if _embed_hook is not None:
            vec = _embed_hook(crop, want)
        elif want == METHOD_CLIP:
            vec = embed_clip(crop)
            if vec is None:
                want = METHOD_HIST
                vec = embed_image(crop)
        else:
            vec = embed_image(crop)
    except Exception:  # noqa: BLE001
        return None
    if vec is None:
        return None
    arr = np.asarray(vec, dtype=np.float32).reshape(-1)
    if det_id:
        upsert_embedding(det_id, want, mtime, arr.tobytes(), int(arr.size))
    return arr, want


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def find_similar(detection_id: str, top_k: int = 12, same_class: bool = True) -> dict[str, Any]:
    probe = get_detection(detection_id)
    if probe is None or probe.get("is_deleted"):
        raise ValueError("detection not found")
    crop = _resolve_crop(probe)
    if crop is None:
        raise ValueError("detection has no crop")

    method = active_method()
    probe_out = embed_for_row(probe, method=method)
    if probe_out is None:
        raise ValueError("detection has no crop")
    probe_vec, method = probe_out

    class_name = str(probe.get("class_name") or "")
    candidates = list_detections(include_deleted=False)
    scored: list[dict[str, Any]] = []
    considered = 0
    for row in candidates:
        if str(row["id"]) == detection_id:
            continue
        if same_class and class_name and str(row.get("class_name")) != class_name:
            continue
        other_crop = _resolve_crop(row)
        if other_crop is None:
            continue
        considered += 1
        if considered > CANDIDATE_LIMIT:
            break
        try:
            other = embed_for_row(row, method=method)
            if other is None:
                continue
            other_vec, other_method = other
            if other_method != method:
                continue
            sim = cosine(probe_vec, other_vec)
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
        "method": method,
        "same_class": same_class,
        "results": scored[:top_k],
    }
