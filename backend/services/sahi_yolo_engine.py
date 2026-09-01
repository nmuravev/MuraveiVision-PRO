"""SAHI (Slicing Aided Hyper Inference) wrapper around the live YOLO engine.

Reuses the already-loaded Ultralytics model from ``YoloEngine`` (no duplicate
VRAM). Slices the frame into overlapping patches, runs the engine's
``_run_model`` on each slice, remaps normalized bboxes back to full-frame
coordinates, and returns the merged object list. The caller
(``YoloEngine.infer_sahi``) applies NMS, drop-outer, tracking, and the response
envelope — identical contract to the fast path.

If SAHI is not installed or slicing fails, the wrapper degrades gracefully to a
single full-frame ``_run_model`` call so the API never 500s.
"""
from __future__ import annotations

import io
from typing import Any


def slice_and_detect(
    engine: Any,
    img: Any,
    floor: float,
    slice_height: int = 512,
    slice_width: int = 512,
    overlap_ratio: float = 0.2,
) -> list[dict[str, Any]]:
    """Slice ``img`` (PIL RGB) and run ``engine._run_model`` per slice.

    Returns merged object dicts with bbox normalized to the full frame.
    No NMS is applied here — the caller merges/dedupes.
    """
    try:
        from sahi.slicing import slice_image
    except ImportError:
        # SAHI not installed — degrade to single full-frame inference.
        return engine._run_model(engine.model, img, floor)

    w, h = img.size
    # Don't slice if the frame is already smaller than one tile.
    if w <= slice_width and h <= slice_height:
        return engine._run_model(engine.model, img, floor)

    import numpy as np
    from PIL import Image as _PILImage

    try:
        sliced = slice_image(
            np.array(img),
            slice_height=slice_height,
            slice_width=slice_width,
            overlap_height_ratio=overlap_ratio,
            overlap_width_ratio=overlap_ratio,
            auto_slice_resolution=False,
            verbose=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[SAHI] slice_image failed, fallback to full-frame: {exc}")
        return engine._run_model(engine.model, img, floor)

    images = getattr(sliced, "images", None) or []
    starts = getattr(sliced, "starting_pixels", None) or []
    if not images or len(images) != len(starts):
        return engine._run_model(engine.model, img, floor)

    objects: list[dict[str, Any]] = []
    for crop_np, start in zip(images, starts):
        try:
            x0, y0 = int(start[0]), int(start[1])
        except Exception:  # noqa: BLE001
            continue
        try:
            crop = _PILImage.fromarray(crop_np.astype("uint8")).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            print(f"[SAHI] crop convert skip: {exc}")
            continue
        cw, ch = crop.size
        for obj in engine._run_model(engine.model, crop, floor):
            bbox = obj["bbox"]
            obj["bbox"] = {
                "x1": max(0.0, min(1.0, (bbox["x1"] * cw + x0) / w)),
                "y1": max(0.0, min(1.0, (bbox["y1"] * ch + y0) / h)),
                "x2": max(0.0, min(1.0, (bbox["x2"] * cw + x0) / w)),
                "y2": max(0.0, min(1.0, (bbox["y2"] * ch + y0) / h)),
            }
            objects.append(obj)
    return objects


def predict_with_sahi(
    engine: Any,
    image_bytes: bytes,
    confidence: float = 0.25,
    frame_idx: int = 0,
    time_sec: float = 0.0,
    viewer_id: str = "default",
    slice_height: int = 512,
    slice_width: int = 512,
    overlap_ratio: float = 0.2,
) -> Any:
    """Async convenience entrypoint used by scripts/tests.

    Delegates to ``engine.infer_sahi`` so the full queue/tracking/envelope
    pipeline runs. Returns an awaitable dict envelope identical to the fast
    path plus ``"sahi": True``.
    """
    return engine.infer_sahi(
        image_bytes,
        confidence,
        frame_idx,
        time_sec,
        viewer_id=viewer_id,
        slice_height=slice_height,
        slice_width=slice_width,
        overlap_ratio=overlap_ratio,
    )
