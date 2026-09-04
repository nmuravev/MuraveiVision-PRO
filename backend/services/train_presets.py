"""Load 3D gsplat train presets from config/train_presets.json (repo root)."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from services.runtime_log import write as runtime_write
from services.security import BASE_DIR

PRESETS_PATH = BASE_DIR / "config" / "train_presets.json"

_BUILTIN: dict[str, dict[str, Any]] = {
    "bootstrap": {
        "label": "Bootstrap",
        "script": "bootstrap",
        "max_points": 80000,
        "eta": "≈30с",
    },
    "balanced": {
        "label": "Balanced",
        "script": "gsplat",
        "max_steps": 7000,
        "data_factor": 4,
        "eta": "5–10 мин",
        "default": True,
    },
    "high": {
        "label": "High Quality",
        "script": "gsplat",
        "max_steps": 30000,
        "data_factor": 4,
        "eta": "15–30 мин",
        "min_vram_gb": 12,
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
        if script not in ("bootstrap", "gsplat"):
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
        else:
            entry["max_points"] = int(val.get("max_points") or 80_000)
        if "min_vram_gb" in val:
            entry["min_vram_gb"] = float(val["min_vram_gb"])
        if val.get("default"):
            entry["default"] = True
        out[key] = entry
    if "balanced" not in out and "bootstrap" not in out:
        return None
    return out


def load_presets() -> tuple[dict[str, dict[str, Any]], bool]:
    """Return (presets, from_file). Falls back to built-in Balanced set."""
    if PRESETS_PATH.is_file():
        try:
            raw = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
            validated = _validate(raw)
            if validated:
                return validated, True
            runtime_write(
                "warn",
                "recon_train",
                f"Invalid train presets at {PRESETS_PATH.name} — using built-in Balanced",
            )
        except (OSError, json.JSONDecodeError) as exc:
            runtime_write(
                "warn",
                "recon_train",
                f"Failed to read train presets: {exc} — using built-in Balanced",
            )
    else:
        runtime_write(
            "warn",
            "recon_train",
            "config/train_presets.json missing — using built-in Balanced",
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
    from services.gsplat_msvc import gsplat_train_ready

    presets, _ = load_presets()
    vram = total_vram_gb()
    msvc_ok, msvc_reason = gsplat_train_ready()
    items: list[dict[str, Any]] = []
    for pid, cfg in presets.items():
        min_v = float(cfg.get("min_vram_gb") or 0)
        script = str(cfg.get("script") or "")
        disabled = bool(min_v and vram > 0 and vram < min_v)
        reason = ""
        if disabled:
            reason = f"Нужно ≥{min_v:g} ГБ VRAM (сейчас {vram:.1f} ГБ)"
        elif vram <= 0 and min_v:
            reason = f"Нужно ≥{min_v:g} ГБ VRAM (CUDA недоступна)"
            disabled = True
        elif script == "gsplat" and not msvc_ok:
            disabled = True
            reason = msvc_reason or "Нужен MSVC 14.44 (см. ENGINEER_GUIDE) или пресет Bootstrap"
        items.append(
            {
                "id": pid,
                "label": cfg.get("label") or pid,
                "eta": cfg.get("eta") or "",
                "default": bool(cfg.get("default")),
                "disabled": disabled,
                "disabled_reason": reason,
            }
        )
    # Stable order: bootstrap, balanced, high, then others
    order = {"bootstrap": 0, "balanced": 1, "high": 2}
    items.sort(key=lambda x: (order.get(x["id"], 99), x["id"]))
    return items
