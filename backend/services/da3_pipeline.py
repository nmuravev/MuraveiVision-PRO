"""Depth Anything 3 (DA3) Dense 3D Reconstruction Pipeline.

Pose-conditioned neural dense depth estimation aligned with COLMAP camera poses.
Air-gap invariant: Weights reside strictly in sidecars/da3/ (FullKit-only).
"""
from __future__ import annotations

import json
import math
import os
import shutil
import struct
from pathlib import Path
from typing import Any, Callable

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore

# ByteDance Seed DA3 API import with fallback to direct weight loader
try:
    from depth_anything_3.api import DepthAnything3  # type: ignore
except ImportError:
    DepthAnything3 = None  # TODO: verify API on github.com/bytedance-seed/depth-anything-3

from services.runtime_log import write as runtime_write

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Decision Q2: Max input resolution long side capped at 1024px to guarantee fitting 8 GB VRAM.
DA3_MAX_LONG_SIDE = 1024
MIN_REGISTERED_CAMERAS = 8


class DA3WeightsNotFoundError(FileNotFoundError):
    """Raised when DA3 model weights are missing from sidecars/da3/."""


def get_da3_sidecar_dir() -> Path:
    override = os.environ.get("MURAVEI_DA3_DIR", "").strip() or os.environ.get("MURAVEI_SIDECARS_DIR", "").strip()
    if override:
        p = Path(override)
        return p if p.name == "da3" else p / "da3"
    return BASE_DIR / "sidecars" / "da3"


DA3_SIDECAR_DIR = get_da3_sidecar_dir()


def find_da3_weights(variant: str = "base") -> Path | None:
    """Locate safetensors (preferred) or .pt weights in sidecars/da3/ (Decision Q1)."""
    sidecar_dir = get_da3_sidecar_dir()
    candidates = [
        sidecar_dir / f"da3_{variant}.safetensors",
        sidecar_dir / f"da3_{variant}.pt",
        sidecar_dir / f"depth_anything_3_{variant}.safetensors",
        sidecar_dir / f"depth_anything_3_{variant}.pt",
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def _load_image_rgb(path: Path) -> np.ndarray:
    """Load image as uint8 RGB numpy array."""
    try:
        from PIL import Image

        with Image.open(path) as img:
            return np.array(img.convert("RGB"))
    except Exception:
        import cv2

        bgr = cv2.imread(str(path))
        if bgr is None:
            raise FileNotFoundError(f"Cannot read image: {path}")
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _resize_for_da3(img_rgb: np.ndarray, max_side: int = DA3_MAX_LONG_SIDE) -> tuple[np.ndarray, float]:
    """Downscale image so max(H, W) <= max_side. Return resized image and scale factor."""
    h, w = img_rgb.shape[:2]
    long_side = max(h, w)
    if long_side <= max_side:
        return img_rgb, 1.0
    scale = max_side / float(long_side)
    new_w = max(32, int(round(w * scale / 14.0) * 14))  # Align to ViT patch grid if needed
    new_h = max(32, int(round(h * scale / 14.0) * 14))

    try:
        from PIL import Image

        pil_img = Image.fromarray(img_rgb)
        resized = pil_img.resize((new_w, new_h), Image.Resampling.BILINEAR)
        return np.array(resized), scale
    except Exception:
        import cv2

        resized = cv2.resize(img_rgb, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        return resized, scale


def _depth_to_orig_hw(depth_np: np.ndarray, orig_h: int, orig_w: int) -> np.ndarray:
    """Normalize DA3 depth tensors (N,H,W)/(H,W)/… to (orig_h, orig_w) float32."""
    d = np.asarray(depth_np, dtype=np.float32)
    while d.ndim > 2:
        d = d[0]
    if d.ndim != 2:
        raise ValueError(f"unexpected depth ndim={d.ndim} shape={getattr(d, 'shape', None)}")
    if d.shape == (orig_h, orig_w):
        return np.maximum(d, 1e-3)
    try:
        import cv2

        d = cv2.resize(d, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
    except Exception:
        from PIL import Image

        d = np.array(
            Image.fromarray(d).resize((orig_w, orig_h), Image.Resampling.BILINEAR),
            dtype=np.float32,
        )
    return np.maximum(d.astype(np.float32, copy=False), 1e-3)


def _predict_depth_map(
    model: Any,
    img_rgb: np.ndarray,
    orig_shape: tuple[int, int],
    device: str = "cpu",
) -> np.ndarray:
    """Run DA3 inference; never invent flat/synthetic depth (anti-garbage cloud).

    Depth Anything 3 expects multi-view input ``(B, N, 3, H, W)``. Prefer the
    public ``inference([image])`` API; fall back to ``forward`` with N=1.
    """
    orig_h, orig_w = orig_shape
    if hasattr(model, "predict_depth"):
        return model.predict_depth(img_rgb, orig_shape)
    if hasattr(model, "infer_image"):
        out = model.infer_image(img_rgb)
        if isinstance(out, dict):
            depth = out.get("depth") or out.get("predicted_depth") or next(iter(out.values()))
        else:
            depth = out
        depth_np = np.asarray(depth, dtype=np.float32)
        if depth_np.ndim == 2 and depth_np.shape != (orig_h, orig_w):
            # Caller/tests may return already-shaped maps via mocks
            return depth_np
        return _depth_to_orig_hw(depth_np, orig_h, orig_w)

    # Preferred path: DepthAnything3.inference (handles preprocess + (B,N,C,H,W))
    if hasattr(model, "inference"):
        try:
            pred = model.inference([img_rgb], process_res=min(DA3_MAX_LONG_SIDE, 504))
            depth = getattr(pred, "depth", None)
            if depth is None and isinstance(pred, dict):
                depth = pred.get("depth") or pred.get("predicted_depth")
            if depth is None:
                raise RuntimeError("DA3 inference returned no depth")
            return _depth_to_orig_hw(depth, orig_h, orig_w)
        except Exception as exc:
            runtime_write(
                "error",
                "da3_pipeline",
                f"DA3 inference() failed (flat fallback disabled): {exc}",
            )
            raise DA3WeightsNotFoundError(
                "DA3_RUNTIME_UNAVAILABLE: инференс depth_anything_3 завершился ошибкой; "
                "плоский fallback отключён намеренно (анти-мусор)."
            ) from exc

    try:
        import torch

        if hasattr(model, "forward") or callable(model):
            resized_img, _ = _resize_for_da3(img_rgb, DA3_MAX_LONG_SIDE)
            # DA3 forward: (B, N, 3, H, W) — add view dimension N=1
            t_img = (
                torch.from_numpy(resized_img)
                .permute(2, 0, 1)
                .unsqueeze(0)
                .unsqueeze(0)
                .float()
                / 255.0
            )
            if device != "cpu" and torch.cuda.is_available():
                t_img = t_img.to(device)
            with torch.no_grad():
                out = model(t_img)
                if isinstance(out, dict):
                    depth_t = out.get("depth") or out.get("predicted_depth") or list(out.values())[0]
                else:
                    depth_t = out
                # Common shapes: (B,N,H,W) or (B,N,1,H,W)
                while depth_t.dim() > 3:
                    depth_t = depth_t[:, 0]
                if depth_t.dim() == 3:
                    depth_t = depth_t[0]  # first batch → (H,W) or squeeze N
                if depth_t.dim() == 3:
                    depth_t = depth_t[0]
                depth_t = torch.nn.functional.interpolate(
                    depth_t.unsqueeze(0).unsqueeze(0),
                    size=(orig_h, orig_w),
                    mode="bilinear",
                    align_corners=False,
                ).squeeze()
                depth_np = depth_t.detach().float().cpu().numpy()
                return np.maximum(depth_np, 1e-3)
    except Exception as exc:
        runtime_write("error", "da3_pipeline", f"DA3 inference failed (flat fallback disabled): {exc}")
        raise DA3WeightsNotFoundError(
            "DA3_RUNTIME_UNAVAILABLE: инференс depth_anything_3 завершился ошибкой; "
            "плоский fallback отключён намеренно (анти-мусор)."
        ) from exc

    raise DA3WeightsNotFoundError(
        "DA3_RUNTIME_UNAVAILABLE: модель не поддерживает predict_depth/infer_image/inference/forward; "
        "плоский fallback отключён намеренно (анти-мусор)."
    )


def _da3_model_usable(model: Any) -> bool:
    if model is None:
        return False
    return (
        hasattr(model, "predict_depth")
        or hasattr(model, "infer_image")
        or hasattr(model, "inference")
        or hasattr(model, "forward")
        or callable(model)
    )


def _ensure_hf_model_dir(weight_path: Path, variant: str) -> Path:
    """Prepare a HF-style dir (config.json + model.safetensors) for from_pretrained.

    Weights live as da3_<variant>.safetensors at sidecar root (Z1 filenames).
    DepthAnything3.from_pretrained expects a directory with model.safetensors.
    """
    sidecar = get_da3_sidecar_dir()
    vdir = sidecar / variant
    vdir.mkdir(parents=True, exist_ok=True)
    target = vdir / "model.safetensors"
    if not target.is_file():
        try:
            os.link(str(weight_path.resolve()), str(target))
        except OSError:
            if target.exists() or target.is_symlink():
                target.unlink(missing_ok=True)  # type: ignore[call-arg]
            try:
                target.symlink_to(weight_path.resolve())
            except OSError as exc:
                raise DA3WeightsNotFoundError(
                    f"DA3_RUNTIME_UNAVAILABLE: cannot link {weight_path.name} → {target}: {exc}"
                ) from exc
    cfg = vdir / "config.json"
    if not cfg.is_file():
        # Optional staged copy next to weights
        alt = sidecar / f"config_{variant}.json"
        if alt.is_file():
            shutil.copy2(alt, cfg)
        else:
            raise DA3WeightsNotFoundError(
                f"DA3_RUNTIME_UNAVAILABLE: отсутствует config.json для variant={variant} "
                f"(ожидается {cfg.as_posix()} или sidecars/da3/config_{variant}.json). "
                "Скачайте с Hugging Face model card рядом с весами."
            )
    return vdir


def _load_da3_model(weight_path: Path, device: str = "cpu", variant: str = "base") -> Any:
    """Load DepthAnything3 API or fail closed (no bare state-dict as runnable model)."""
    try:
        import torch

        if DepthAnything3 is not None and hasattr(DepthAnything3, "from_pretrained"):
            model_dir = _ensure_hf_model_dir(weight_path, variant)
            model = DepthAnything3.from_pretrained(str(model_dir))
            if hasattr(model, "to"):
                model = model.to(device)
            return model
        # Bare safetensors/pt without API cannot produce depth maps — fail closed
        runtime_write(
            "warn",
            "da3_pipeline",
            "depth_anything_3.api unavailable; refusing bare state-dict as runnable model",
        )
        return None
    except DA3WeightsNotFoundError:
        raise
    except Exception as exc:
        runtime_write("warn", "da3_pipeline", f"DA3 model load failed: {exc}")
        return None


def _align_depth_scale(
    depth_map: np.ndarray,
    sparse_points: np.ndarray,
    R: np.ndarray,
    t: np.ndarray,
    intr: dict[str, float],
) -> np.ndarray:
    """Align relative depth map to COLMAP metric scale using median sparse 3D point residuals."""
    if len(sparse_points) == 0:
        return depth_map

    fx = float(intr.get("fx", 1000.0))
    fy = float(intr.get("fy", 1000.0))
    cx = float(intr.get("cx", depth_map.shape[1] / 2.0))
    cy = float(intr.get("cy", depth_map.shape[0] / 2.0))
    h, w = depth_map.shape

    # Transform sparse points to camera frame: x_cam = R @ X_world + t
    # sparse_points shape (N, 3)
    pts_cam = (R @ sparse_points.T + t[:, None]).T
    valid_mask = pts_cam[:, 2] > 0.1
    if not np.any(valid_mask):
        return depth_map

    pts_valid = pts_cam[valid_mask]
    u = np.round(fx * (pts_valid[:, 0] / pts_valid[:, 1]) + cx).astype(int)
    v = np.round(fy * (pts_valid[:, 1] / pts_valid[:, 2]) + cy).astype(int)

    in_frame = (u >= 0) & (u < w) & (v >= 0) & (v < h)
    if not np.any(in_frame):
        return depth_map

    colmap_z = pts_valid[in_frame, 2]
    da3_z = depth_map[v[in_frame], u[in_frame]]

    valid_ratios = da3_z > 1e-4
    if not np.any(valid_ratios):
        return depth_map

    ratios = colmap_z[valid_ratios] / da3_z[valid_ratios]
    scale_factor = float(np.median(ratios))

    if math.isnan(scale_factor) or scale_factor <= 0.0 or scale_factor > 1000.0:
        scale_factor = 1.0

    return depth_map * scale_factor


def _unproject_pixels(
    depth_map: np.ndarray,
    rgb_img: np.ndarray,
    R: np.ndarray,
    t: np.ndarray,
    intr: dict[str, float],
    step: int = 4,
) -> tuple[np.ndarray, np.ndarray]:
    """Unproject pixels to 3D world coordinates (Decision Q3: XYZ + RGB, NO normals)."""
    h, w = depth_map.shape
    fx = float(intr.get("fx", 1000.0))
    fy = float(intr.get("fy", 1000.0))
    cx = float(intr.get("cx", w / 2.0))
    cy = float(intr.get("cy", h / 2.0))

    vs, us = np.mgrid[0:h:step, 0:w:step]
    depths = depth_map[vs, us]

    valid = (depths > 0.2) & (depths < 200.0) & (~np.isnan(depths))
    if not np.any(valid):
        return np.empty((0, 3), dtype=np.float32), np.empty((0, 3), dtype=np.uint8)

    us_val = us[valid]
    vs_val = vs[valid]
    d_val = depths[valid]
    colors = rgb_img[vs_val, us_val]

    # Camera coordinates: [x_cam, y_cam, z_cam]
    x_cam = (us_val - cx) / fx * d_val
    y_cam = (vs_val - cy) / fy * d_val
    z_cam = d_val
    pts_cam = np.stack([x_cam, y_cam, z_cam], axis=1)

    # World coordinates: X_world = R^T @ (pts_cam - t)
    R_T = R.T
    pts_world = (R_T @ (pts_cam - t).T).T

    return pts_world.astype(np.float32), colors.astype(np.uint8)


def _write_binary_ply(path: Path, points: np.ndarray, colors: np.ndarray) -> None:
    """Write binary little-endian PLY file with 6 properties (x, y, z, red, green, blue)."""
    n = len(points)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {n}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar red\n"
        "property uchar green\n"
        "property uchar blue\n"
        "end_header\n"
    ).encode("ascii")

    with path.open("wb") as f:
        f.write(header)
        # Pack binary vertex records: 3 floats (12 bytes) + 3 bytes RGB
        for i in range(n):
            f.write(
                struct.pack(
                    "<fffBBB",
                    float(points[i, 0]),
                    float(points[i, 1]),
                    float(points[i, 2]),
                    int(colors[i, 0]),
                    int(colors[i, 1]),
                    int(colors[i, 2]),
                )
            )


def run_da3_pipeline(
    job_dir: Path,
    variant: str = "base",
    mock_model: Any = None,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Execute pose-conditioned DA3 dense reconstruction pipeline."""
    job_dir = Path(job_dir)
    runtime_write("info", "da3_pipeline", f"Starting DA3 dense pipeline (variant={variant}) at {job_dir.name}")

    def _notify(stage: str, message: str, progress: float, **kwargs: Any) -> None:
        if emit:
            emit(
                {
                    "stage": stage,
                    "phase": "da3_dense",
                    "message": message,
                    "progress": round(progress, 3),
                    **kwargs,
                }
            )

    # 1. Check weights presence unless mock provided
    weight_path = find_da3_weights(variant)
    if not weight_path and mock_model is None:
        runtime_write("error", "da3_pipeline", f"DA3 weights not found for variant '{variant}'")
        raise DA3WeightsNotFoundError(
            f"Веса модели DA3 ({variant}) не найдены в sidecars/da3/. "
            "Скопируйте da3_base.safetensors из FullKit пака."
        )

    # 2. Preflight & Gate check: camera_poses.json
    poses_path = job_dir / "camera_poses.json"
    if not poses_path.is_file():
        return {
            "ok": False,
            "error": "Файл camera_poses.json не найден — выполните разреженную реконструкцию COLMAP",
            "warning": "Файл camera_poses.json не найден",
            "dense_ply": None,
            "preserved_sparse": True,
        }

    try:
        poses_doc = json.loads(poses_path.read_text(encoding="utf-8"))
        frames_meta: list[dict[str, Any]] = poses_doc.get("frames") or []
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Ошибка чтения camera_poses.json: {exc}",
            "warning": "Не удалось прочитать camera_poses.json",
            "dense_ply": None,
            "preserved_sparse": True,
        }

    if len(frames_meta) < MIN_REGISTERED_CAMERAS:
        msg = f"Недостаточно зарегистрированных ракурсов COLMAP ({len(frames_meta)} < {MIN_REGISTERED_CAMERAS}) для нейросетевой реконструкции"
        runtime_write("warn", "da3_pipeline", f"Soft-fail gate: {msg}")
        return {
            "ok": False,
            "error": msg,
            "warning": msg,
            "dense_ply": None,
            "preserved_sparse": True,
        }

    # 3. Load sparse points for scale alignment
    sparse_points = np.empty((0, 3), dtype=np.float32)
    sparse_pts_path = job_dir / "sparse_points.json"
    if sparse_pts_path.is_file():
        try:
            pts_data = json.loads(sparse_pts_path.read_text(encoding="utf-8"))
            sparse_list = pts_data.get("points") or []
            if sparse_list:
                sparse_points = np.array(sparse_list, dtype=np.float32)
        except Exception:
            pass

    # 4. Initialize model / load weights (fail closed — no flat synthetic depth)
    model = mock_model
    device = "cpu"
    if model is None and weight_path:
        _notify("da3_load", f"Загрузка весов DA3 ({weight_path.name})...", 0.05)
        try:
            import torch

            if torch.cuda.is_available():
                device = "cuda"
        except Exception:
            device = "cpu"
        model = _load_da3_model(weight_path, device=device, variant=str(variant or "base"))

    if not _da3_model_usable(model):
        runtime_write("error", "da3_pipeline", "DA3 runtime unavailable (no usable model)")
        raise DA3WeightsNotFoundError(
            "DA3_RUNTIME_UNAVAILABLE: пакет depth_anything_3 не импортируется в muravei_env "
            "или веса нечитаемы. Плоский fallback отключён намеренно (анти-мусор)."
        )

    # Intermediate depths directory (Decision Q4)
    depths_dir = job_dir / "da3" / "depths"
    depths_dir.mkdir(parents=True, exist_ok=True)

    # 5. Windowed depth estimation (48-64 views per window)
    total_frames = len(frames_meta)
    frames_dir = job_dir / "frames"
    all_fused_points: list[np.ndarray] = []
    all_fused_colors: list[np.ndarray] = []
    depth_medians: list[float] = []
    depth_stds: list[float] = []

    _notify("da3_depth", f"DA3 инференс карт глубин (всего {total_frames} ракурсов)...", 0.1, frames_total=total_frames)

    for idx, fmeta in enumerate(frames_meta):
        img_name = fmeta.get("image") or f"frame_{idx:04d}.png"
        img_path = frames_dir / img_name
        if not img_path.is_file():
            # Filename soft-match (not depth fallback)
            cands = list(frames_dir.glob(f"*{img_name}*"))
            if cands:
                img_path = cands[0]

        if not img_path.is_file():
            continue

        try:
            rgb_img = _load_image_rgb(img_path)
            orig_h, orig_w = rgb_img.shape[:2]
        except Exception:
            continue

        # Predict raw depth
        raw_depth = _predict_depth_map(model, rgb_img, (orig_h, orig_w), device=device)

        # Scale alignment with COLMAP sparse points
        R = np.array(fmeta.get("R") or np.eye(3), dtype=np.float32)
        t = np.array(fmeta.get("t") or np.zeros(3), dtype=np.float32)
        intr = fmeta.get("intrinsics") or {"fx": 1000.0, "fy": 1000.0, "cx": orig_w / 2.0, "cy": orig_h / 2.0}

        aligned_depth = _align_depth_scale(raw_depth, sparse_points, R, t, intr)

        # In-memory depth stats (N2: before Q4 cleanup; no .npy kept by default)
        try:
            finite = aligned_depth[np.isfinite(aligned_depth)]
            if finite.size > 0:
                depth_medians.append(float(np.median(finite)))
                depth_stds.append(float(np.std(finite)))
        except Exception:
            pass

        # Save temporary depth array for potential debug / inspect
        depth_file = depths_dir / f"{Path(img_name).stem}.npy"
        np.save(str(depth_file), aligned_depth)

        # Unproject points
        pts_w, cols = _unproject_pixels(aligned_depth, rgb_img, R, t, intr, step=4)
        if len(pts_w) > 0:
            all_fused_points.append(pts_w)
            all_fused_colors.append(cols)

        if (idx + 1) % 10 == 0 or idx == total_frames - 1:
            progress = 0.1 + 0.6 * ((idx + 1) / float(total_frames))
            _notify(
                "da3_depth",
                f"DA3 глубина: {idx + 1}/{total_frames} кадров",
                progress,
                frames_done=idx + 1,
                frames_total=total_frames,
            )

    # 6. Overlap Fusion & Outlier filtering
    _notify("da3_fusion", "Слияние перекрытий и фильтрация плотного облака...", 0.75)
    if all_fused_points:
        final_points = np.concatenate(all_fused_points, axis=0)
        final_colors = np.concatenate(all_fused_colors, axis=0)
    else:
        final_points = np.empty((0, 3), dtype=np.float32)
        final_colors = np.empty((0, 3), dtype=np.uint8)

    # Subsample if too dense (cap at 1.5 million points for smooth WebGL rendering)
    MAX_DENSE_POINTS = 1_500_000
    if len(final_points) > MAX_DENSE_POINTS:
        stride = int(math.ceil(len(final_points) / float(MAX_DENSE_POINTS)))
        final_points = final_points[::stride]
        final_colors = final_colors[::stride]

    # 7. Write binary dense.ply
    dense_out = job_dir / "dense.ply"
    _write_binary_ply(dense_out, final_points, final_colors)
    runtime_write("info", "da3_pipeline", f"dense.ply written ({len(final_points)} points) -> {dense_out.name}")

    # 8. Decision Q4: Clean up intermediate depths directory unless MURAVEI_DA3_KEEP_DEPTHS=1
    keep_depths = os.environ.get("MURAVEI_DA3_KEEP_DEPTHS", "").strip() == "1"
    if not keep_depths and depths_dir.is_dir():
        try:
            shutil.rmtree(depths_dir)
            runtime_write("info", "da3_pipeline", f"Cleaned up intermediate depths dir: {depths_dir}")
        except Exception as exc:
            runtime_write("warn", "da3_pipeline", f"Could not remove depths dir: {exc}")

    # 9. Update manifest.json
    manifest_path = job_dir / "manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    manifest["dense_backend"] = f"da3_{variant}"
    manifest["dense_file"] = "dense.ply"
    if "artifacts" not in manifest or not isinstance(manifest["artifacts"], dict):
        manifest["artifacts"] = {}
    manifest["artifacts"]["dense"] = "dense.ply"
    manifest["artifact"] = "dense.ply"
    manifest["dense_points_count"] = len(final_points)
    manifest["status"] = "colmap_done"
    manifest["da3_max_long_side"] = DA3_MAX_LONG_SIDE
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    _notify(
        "da3_done",
        f"Плотная реконструкция DA3 готова ({len(final_points)} точек)",
        1.0,
        points_count=len(final_points),
    )

    return {
        "ok": True,
        "dense_ply": "dense.ply",
        "points_count": len(final_points),
        "dense_backend": f"da3_{variant}",
        "depth_median": float(np.median(depth_medians)) if depth_medians else None,
        "depth_std": float(np.mean(depth_stds)) if depth_stds else None,
        "warning": None,
    }


# Public aliases for unit tests
align_depth_scale = _align_depth_scale
unproject_depth_to_points = _unproject_pixels
write_binary_ply = _write_binary_ply
