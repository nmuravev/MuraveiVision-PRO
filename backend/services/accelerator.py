"""Accelerator profile: CUDA vs CPU (+ DirectML for YOLO on AMD/Intel DX12).

Field target without NVIDIA (e.g. Intel MacBook + AMD Radeon Boot Camp) uses the
CPU profile: COLMAP CPU budgets, Dense/Mesh gated, gsplat disabled.
Force with env ``MURAVEI_FORCE_ACCELERATOR=cpu|cuda`` (tests / smoke).
"""
from __future__ import annotations

import os
from typing import Any, Literal

AcceleratorKind = Literal["cuda", "cpu"]

CPU_BANNER_RU = "Нет NVIDIA GPU — режим CPU + DirectML (если доступен)"
GSPLAT_CUDA_REASON_RU = "требуется NVIDIA CUDA"
CPU_DENSE_ETA_RU = "CPU: 1–3 часа"
CPU_DENSE_DISABLED_RU = (
    f"CPU-профиль: Dense/Mesh отключены (нет NVIDIA CUDA). {CPU_DENSE_ETA_RU}."
)

# COLMAP budgets when accelerator_kind()=="cpu" (env COLMAP_* still wins).
CPU_COLMAP_MAX_IMAGE_SIZE = 1200
CPU_COLMAP_MAX_FRAMES = 250  # mid of 150–300
CPU_DENSE_MAX_FRAMES = 100

_profile_logged = False


def accelerator_kind() -> AcceleratorKind:
    forced = (os.environ.get("MURAVEI_FORCE_ACCELERATOR") or "").strip().lower()
    if forced in ("cpu", "cuda"):
        return forced  # type: ignore[return-value]
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:  # noqa: BLE001
        pass
    return "cpu"


def is_cpu_profile() -> bool:
    return accelerator_kind() == "cpu"


def colmap_use_gpu() -> bool:
    """COLMAP SIFT GPU only when CUDA profile is active."""
    forced = (os.environ.get("COLMAP_USE_GPU") or "").strip().lower()
    if forced in ("0", "false", "no", "off"):
        return False
    if forced in ("1", "true", "yes", "on"):
        return True
    return not is_cpu_profile()


def cpu_dense_mesh_disabled() -> bool:
    """Config flag: disable Dense/Mesh entirely on CPU (default on)."""
    if not is_cpu_profile():
        return False
    raw = (os.environ.get("MURAVEI_CPU_DISABLE_DENSE") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def dense_frame_cap() -> int | None:
    """Max frames to copy into AliceVision when on CPU profile; None = no cap."""
    if not is_cpu_profile():
        return None
    raw = (os.environ.get("MURAVEI_CPU_DENSE_MAX_FRAMES") or "").strip()
    if raw:
        try:
            return max(8, min(500, int(raw)))
        except ValueError:
            pass
    return CPU_DENSE_MAX_FRAMES


def profile_snapshot() -> dict[str, Any]:
    kind = accelerator_kind()
    return {
        "accelerator_kind": kind,
        "cpu_profile": kind == "cpu",
        "banner": CPU_BANNER_RU if kind == "cpu" else "",
        "colmap_use_gpu": colmap_use_gpu(),
        "colmap_max_image_size_default": (
            CPU_COLMAP_MAX_IMAGE_SIZE if kind == "cpu" else None
        ),
        "colmap_max_frames_default": (
            CPU_COLMAP_MAX_FRAMES if kind == "cpu" else None
        ),
        "dense_mesh_disabled": cpu_dense_mesh_disabled(),
        "dense_frame_cap": dense_frame_cap(),
        "gsplat_reason": GSPLAT_CUDA_REASON_RU if kind == "cpu" else "",
        "force_env": (os.environ.get("MURAVEI_FORCE_ACCELERATOR") or "").strip() or None,
    }


def log_profile_once() -> None:
    """Emit one runtime + print line when profile is first resolved."""
    global _profile_logged
    if _profile_logged:
        return
    _profile_logged = True
    snap = profile_snapshot()
    msg = (
        f"accelerator_kind={snap['accelerator_kind']} "
        f"cpu_profile={snap['cpu_profile']} "
        f"colmap_gpu={snap['colmap_use_gpu']} "
        f"dense_disabled={snap['dense_mesh_disabled']}"
    )
    print(f"[accelerator] {msg}")
    try:
        from services.runtime_log import write as runtime_write

        runtime_write("info", "accelerator", msg)
    except Exception:  # noqa: BLE001
        pass


def clear_profile_log_flag() -> None:
    """Test helper."""
    global _profile_logged
    _profile_logged = False
