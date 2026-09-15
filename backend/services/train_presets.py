"""Load 3D recon train presets from config/train_presets.json (repo root)."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from services.runtime_log import write as runtime_write
from services.security import BASE_DIR

PRESETS_PATH = BASE_DIR / "config" / "train_presets.json"

_PRIMARY_ORDER = ("sparse", "dense", "da3_dense_base", "da3_dense_large", "mesh", "splat")
_ALIAS_ORDER = ("bootstrap", "balanced", "high")

_BUILTIN: dict[str, dict[str, Any]] = {
    "sparse": {
        "label": "Sparse",
        "script": "colmap_only",
        "eta": "готово после COLMAP",
        "backend": "colmap_only",
    },
    "dense": {
        "label": "Dense",
        "script": "alicevision_mvs",
        "eta": "10–40 мин",
        "min_vram_gb": 6,
        "backend": "alicevision_mvs",
    },
    "da3_dense_base": {
        "label": "DA3-BASE (Dense)",
        "script": "da3_dense",
        "variant": "base",
        "eta": "30–60с",
        "min_vram_gb": 6,
        "backend": "da3_dense",
        "license": "Apache-2.0",
    },
    "da3_dense_large": {
        "label": "DA3-LARGE (Dense)",
        "script": "da3_dense",
        "variant": "large",
        "eta": "1–2 мин",
        "min_vram_gb": 8,
        "backend": "da3_dense",
        "license": "CC-BY-NC-4.0",
    },
    "mesh": {
        "label": "Mesh",
        "script": "alicevision_mesh",
        "eta": "20–60 мин",
        "min_vram_gb": 8,
        "backend": "alicevision_mesh",
    },
    "splat": {
        "label": "Splat",
        "script": "gsplat",
        "max_steps": 7000,
        "data_factor": 4,
        "eta": "5–10 мин",
        "default": True,
        "backend": "gsplat",
    },
    "bootstrap": {
        "label": "Bootstrap",
        "script": "bootstrap",
        "max_points": 80000,
        "eta": "≈30с",
        "alias_of": "sparse",
    },
    "balanced": {
        "label": "Balanced",
        "script": "gsplat",
        "max_steps": 7000,
        "data_factor": 4,
        "eta": "5–10 мин",
        "alias_of": "splat",
    },
    "high": {
        "label": "High Quality",
        "script": "gsplat",
        "max_steps": 30000,
        "data_factor": 4,
        "eta": "15–30 мин",
        "min_vram_gb": 12,
        "alias_of": "splat",
    },
}


def _validate(raw: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    if not isinstance(raw, dict) or not raw:
        return None
    out: dict[str, dict[str, Any]] = {}
    for key, val in raw.items():
        if not isinstance(key, str) or not isinstance(val, dict):
            return None
        script = str(val.get("script") or "")
        if script not in ("bootstrap", "gsplat", "alicevision_mvs", "alicevision_mesh", "colmap_only", "da3_dense"):
            return None
        entry = dict(val)
        entry["label"] = str(val.get("label") or key)
        entry["eta"] = str(val.get("eta") or "")
        if script == "gsplat":
            steps = int(val.get("max_steps") or 0)
            if steps < 100 or steps > 200_000:
                return None
            entry["max_steps"] = steps
            entry["data_factor"] = int(val.get("data_factor") or 4)
        elif script == "bootstrap":
            entry["max_points"] = int(val.get("max_points") or 80_000)
        elif script == "da3_dense":
            entry["backend"] = "da3_dense"
            entry["variant"] = str(val.get("variant") or "base")
            entry["license"] = str(val.get("license") or "Apache-2.0")
        elif script in ("alicevision_mvs", "alicevision_mesh", "colmap_only"):
            entry["backend"] = script
        if "min_vram_gb" in val:
            entry["min_vram_gb"] = float(val["min_vram_gb"])
        if val.get("default"):
            entry["default"] = True
        if val.get("alias_of"):
            entry["alias_of"] = str(val["alias_of"])
        out[key] = entry
    if not any(k in out for k in ("balanced", "bootstrap", "sparse", "splat")):
        return None
    return out


def load_presets() -> tuple[dict[str, dict[str, Any]], bool]:
    """Return (presets, from_file). Falls back to built-in hierarchy."""
    if PRESETS_PATH.is_file():
        try:
            raw = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
            validated = _validate(raw)
            if validated:
                return validated, True
            runtime_write(
                "warn",
                "recon_train",
                f"Invalid train presets at {PRESETS_PATH.name} — using built-in hierarchy",
            )
        except (OSError, json.JSONDecodeError) as exc:
            runtime_write(
                "warn",
                "recon_train",
                f"Failed to read train presets: {exc} — using built-in hierarchy",
            )
    else:
        runtime_write(
            "warn",
            "recon_train",
            "config/train_presets.json missing — using built-in hierarchy",
        )
    return deepcopy(_BUILTIN), False


def total_vram_gb() -> float:
    try:
        import torch

        if not torch.cuda.is_available():
            return 0.0
        props = torch.cuda.get_device_properties(0)
        return float(props.total_memory) / (1024**3)
    except Exception:  # noqa: BLE001
        return 0.0


def used_vram_gb() -> float:
    try:
        import torch

        if not torch.cuda.is_available():
            return 0.0
        return float(torch.cuda.memory_allocated(0)) / (1024**3)
    except Exception:  # noqa: BLE001
        return 0.0


def presets_for_client() -> list[dict[str, Any]]:
    from services.accelerator import (
        CPU_DENSE_DISABLED_RU,
        CPU_DENSE_ETA_RU,
        GSPLAT_CUDA_REASON_RU,
        cpu_dense_mesh_disabled,
        is_cpu_profile,
        log_profile_once,
    )
    from services.alicevision import alicevision_available, alicevision_cuda_ready
    from services.gsplat_msvc import gsplat_train_ready

    log_profile_once()
    presets, _ = load_presets()
    vram = total_vram_gb()
    msvc_ok, msvc_reason = gsplat_train_ready()
    av_ok = alicevision_available()
    cuda_ok, cuda_reason = alicevision_cuda_ready()
    cpu = is_cpu_profile()
    items: list[dict[str, Any]] = []
    for pid, cfg in presets.items():
        min_v = float(cfg.get("min_vram_gb") or 0)
        script = str(cfg.get("script") or "")
        disabled = False
        reason = ""
        eta = str(cfg.get("eta") or "")
        if script in ("alicevision_mvs", "alicevision_mesh"):
            if cpu and cpu_dense_mesh_disabled():
                disabled = True
                reason = CPU_DENSE_DISABLED_RU
                eta = CPU_DENSE_ETA_RU
            elif not sys.platform.startswith("win") and not av_ok:
                disabled = True
                reason = "AliceVision только Windows (macOS не поддерживается)"
            elif not av_ok:
                disabled = True
                reason = "AliceVision не установлен (sidecar / ALICEVISION_ROOT)"
            elif not cuda_ok:
                disabled = True
                reason = cuda_reason or "AliceVision dense/mesh требует NVIDIA CUDA"
                if cpu:
                    eta = CPU_DENSE_ETA_RU
                    reason = f"{reason}. {CPU_DENSE_ETA_RU}"
            elif min_v and (vram <= 0 or vram < min_v):
                disabled = True
                reason = (
                    f"Нужно ≥{min_v:g} ГБ VRAM (сейчас {vram:.1f} ГБ)"
                    if vram > 0
                    else f"Нужно ≥{min_v:g} ГБ VRAM (CUDA недоступна)"
                )
            elif cpu:
                eta = CPU_DENSE_ETA_RU
        elif script == "da3_dense":
            from services.da3_pipeline import find_da3_weights

            variant = str(cfg.get("variant") or "base")
            has_weights = find_da3_weights(variant) is not None
            # N3: grey button with cause — CUDA absent OR weights missing (same pattern as Dense/Mesh)
            if cpu or not cuda_ok:
                disabled = True
                reason = cuda_reason or "DA3 Dense требует NVIDIA CUDA"
            elif not has_weights:
                disabled = True
                reason = f"Веса DA3 ({variant}) не найдены в sidecars/da3/ (503 DA3_WEIGHTS_NOT_FOUND)"
            elif min_v and (vram <= 0 or vram < min_v):
                disabled = True
                reason = (
                    f"Нужно ≥{min_v:g} ГБ VRAM (сейчас {vram:.1f} ГБ)"
                    if vram > 0
                    else f"Нужно ≥{min_v:g} ГБ VRAM (CUDA недоступна)"
                )
        elif script == "gsplat":
            if cpu or not cuda_ok:
                disabled = True
                reason = GSPLAT_CUDA_REASON_RU
            elif min_v and vram > 0 and vram < min_v:
                disabled = True
                reason = f"Нужно ≥{min_v:g} ГБ VRAM (сейчас {vram:.1f} ГБ)"
            elif min_v and vram <= 0:
                disabled = True
                reason = GSPLAT_CUDA_REASON_RU
            elif not msvc_ok:
                disabled = True
                reason = msvc_reason or "Нужен MSVC 14.44 (см. ENGINEER_GUIDE) или пресет Bootstrap"
        elif min_v and vram > 0 and vram < min_v:
            disabled = True
            reason = f"Нужно ≥{min_v:g} ГБ VRAM (сейчас {vram:.1f} ГБ)"
        elif min_v and vram <= 0:
            disabled = True
            reason = f"Нужно ≥{min_v:g} ГБ VRAM (CUDA недоступна)"

        items.append(
            {
                "id": pid,
                "label": cfg.get("label") or pid,
                "eta": eta,
                "default": bool(cfg.get("default")),
                "disabled": disabled,
                "disabled_reason": reason,
                "alias_of": cfg.get("alias_of"),
                "backend": cfg.get("backend") or script,
                "license": cfg.get("license"),
                "variant": cfg.get("variant"),
            }
        )
    order = {pid: i for i, pid in enumerate((*_PRIMARY_ORDER, *_ALIAS_ORDER))}
    items.sort(key=lambda x: (order.get(x["id"], 99), x["id"]))
    return items
