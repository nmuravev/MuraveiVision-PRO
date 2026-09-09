"""Experimental YOLO inference via ONNX Runtime DirectML (AMD/Intel DX12).

Optional: never required. Any failure falls back to CPU torch with a logged warning.
ONNX export is cached under config/local (never beside pack weights).
CPU .pt path must not call ensure_onnx_export (C1).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from config import BASE_DIR

_LOG = logging.getLogger("muravei.yolo_directml")

DML_PROVIDER = "DmlExecutionProvider"
_ONNX_CACHE_DIR = BASE_DIR / "config" / "local" / "onnx_cache"


def directml_available() -> bool:
    try:
        import onnxruntime as ort

        return DML_PROVIDER in ort.get_available_providers()
    except Exception:  # noqa: BLE001
        return False


def list_ort_providers() -> list[str]:
    try:
        import onnxruntime as ort

        return list(ort.get_available_providers())
    except Exception:  # noqa: BLE001
        return []


def onnx_cache_path(weights: Path) -> Path:
    """Cache path under config/local — not next to shipped .pt."""
    stem = Path(weights).stem
    return _ONNX_CACHE_DIR / f"{stem}.onnx"


def ensure_onnx_export(weights: Path, *, imgsz: int = 640) -> Path:
    """Export Ultralytics model to ONNX once into config/local; never leave beside .pt."""
    import shutil
    import tempfile

    from services.ultralytics_airgap import ensure_ultralytics_airgap

    ensure_ultralytics_airgap()
    weights = Path(weights)
    if not weights.is_file():
        raise FileNotFoundError(f"weights missing: {weights.name}")
    out = onnx_cache_path(weights)
    if out.is_file() and out.stat().st_mtime >= weights.stat().st_mtime and out.stat().st_size > 1024:
        return out
    try:
        _ONNX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"не удалось создать кэш ONNX: {_ONNX_CACHE_DIR}") from exc
    print(
        f"[YOLO] Экспорт ONNX для DirectML ({weights.name}) → {out.name} "
        "(первый запуск ускорения, CPU-путь не ждёт)…"
    )
    _LOG.info("onnx export start weights=%s out=%s", weights.name, out)
    from ultralytics import YOLO

    # Export inside a temp dir under onnx_cache so Ultralytics never writes next to pack .pt.
    with tempfile.TemporaryDirectory(prefix="onnx_export_", dir=str(_ONNX_CACHE_DIR)) as td:
        tmp_w = Path(td) / weights.name
        shutil.copy2(weights, tmp_w)
        model = YOLO(str(tmp_w))
        exported = model.export(format="onnx", imgsz=int(imgsz), simplify=True, opset=12)
        path = Path(str(exported))
        if not path.is_file():
            # Ultralytics sometimes returns stem without moving; search temp
            hits = list(Path(td).rglob("*.onnx"))
            if not hits:
                raise RuntimeError(f"ONNX export did not produce {out.name}")
            path = hits[0]
        if path.resolve() != out.resolve():
            shutil.copy2(path, out)
        elif not out.is_file():
            raise RuntimeError(f"ONNX export did not produce {out.name}")

    # Belt: remove any sibling .onnx left beside pack weights
    sibling = weights.with_suffix(".onnx")
    if sibling.is_file() and sibling.resolve() != out.resolve():
        try:
            sibling.unlink(missing_ok=True)
            _LOG.info("removed sibling ONNX beside weights: %s", sibling.name)
        except OSError:
            pass
    if not out.is_file():
        raise RuntimeError(f"ONNX export did not produce {out.name}")
    print(f"[YOLO] ONNX готов: {out}")
    return out


def _letterbox(img_rgb, imgsz: int) -> tuple[Any, float, int, int]:
    """Resize with pad to square; return CHW float32 NCHW-ready array, ratio, pad_w, pad_h."""
    import numpy as np
    from PIL import Image

    if not isinstance(img_rgb, Image.Image):
        img_rgb = Image.fromarray(img_rgb)
    img = img_rgb.convert("RGB")
    w, h = img.size
    scale = min(imgsz / max(1, w), imgsz / max(1, h))
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    resized = img.resize((nw, nh), Image.BILINEAR)
    canvas = Image.new("RGB", (imgsz, imgsz), (114, 114, 114))
    pad_x = (imgsz - nw) // 2
    pad_y = (imgsz - nh) // 2
    canvas.paste(resized, (pad_x, pad_y))
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    arr = arr.transpose(2, 0, 1)[None, ...]  # 1x3xHxW
    return arr, scale, pad_x, pad_y


def _parse_yolo_onnx_output(
    output: Any,
    *,
    orig_w: int,
    orig_h: int,
    scale: float,
    pad_x: int,
    pad_y: int,
    conf_thres: float,
) -> list[dict[str, Any]]:
    """Best-effort parse Ultralytics ONNX output (1, C, N) or (1, N, C)."""
    import numpy as np

    arr = np.asarray(output)
    if arr.ndim == 3:
        arr = arr[0]
    # Shape: (4+nc, n) or (n, 4+nc)
    if arr.shape[0] < arr.shape[1] and arr.shape[0] <= 512:
        # (C, N)
        pred = arr.T
    else:
        pred = arr
    if pred.ndim != 2 or pred.shape[1] < 5:
        return []
    boxes: list[dict[str, Any]] = []
    for row in pred:
        scores = row[4:]
        if scores.size == 0:
            continue
        cls_id = int(np.argmax(scores))
        conf = float(scores[cls_id])
        if conf < conf_thres:
            continue
        cx, cy, bw, bh = map(float, row[:4])
        # xywh in letterbox space → original normalized
        x1 = (cx - bw / 2 - pad_x) / scale
        y1 = (cy - bh / 2 - pad_y) / scale
        x2 = (cx + bw / 2 - pad_x) / scale
        y2 = (cy + bh / 2 - pad_y) / scale
        boxes.append(
            {
                "cls_id": cls_id,
                "confidence": conf,
                "bbox": {
                    "x1": max(0.0, min(1.0, x1 / max(1, orig_w))),
                    "y1": max(0.0, min(1.0, y1 / max(1, orig_h))),
                    "x2": max(0.0, min(1.0, x2 / max(1, orig_w))),
                    "y2": max(0.0, min(1.0, y2 / max(1, orig_h))),
                },
            }
        )
    return boxes


def run_directml_onnx(
    onnx_path: Path,
    img: Any,
    *,
    conf: float = 0.25,
    imgsz: int = 640,
) -> list[dict[str, Any]]:
    """Run one ONNX inference with DmlExecutionProvider (CPU EP as ORT fallback list)."""
    import numpy as np
    from PIL import Image

    if not isinstance(img, Image.Image):
        img = Image.fromarray(np.asarray(img))
    orig_w, orig_h = img.size
    tensor, scale, pad_x, pad_y = _letterbox(img, imgsz)

    import onnxruntime as ort

    providers = [DML_PROVIDER, "CPUExecutionProvider"]
    try:
        sess = ort.InferenceSession(str(onnx_path), providers=providers)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "Access is denied" in msg or "os error 5" in msg.lower() or "DLL" in msg.upper():
            raise RuntimeError(
                "ORT DirectML недоступен (DLL/Access denied). "
                "Сессия на CPU .pt; перезапустите для ускорения."
            ) from exc
        raise
    active = sess.get_providers()
    if DML_PROVIDER not in active:
        raise RuntimeError(f"DmlExecutionProvider not active (got {active})")
    inp = sess.get_inputs()[0]
    feeds = {inp.name: tensor.astype(np.float32)}
    outs = sess.run(None, feeds)
    if not outs:
        return []
    return _parse_yolo_onnx_output(
        outs[0],
        orig_w=orig_w,
        orig_h=orig_h,
        scale=scale,
        pad_x=pad_x,
        pad_y=pad_y,
        conf_thres=float(conf),
    )


def select_inference_backend(
    requested: str,
    *,
    torch_cuda: bool,
    dml_ok: bool,
) -> str:
    """
    Resolve backend: 'torch-cuda' | 'directml' | 'cpu'.
    ``requested``: auto | torch | directml
    """
    req = (requested or "auto").strip().lower()
    if req == "directml":
        return "directml" if dml_ok else "cpu"
    if req == "torch":
        return "torch-cuda" if torch_cuda else "cpu"
    # auto
    if torch_cuda:
        return "torch-cuda"
    if dml_ok:
        return "directml"
    return "cpu"
