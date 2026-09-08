"""config/local small flags (CPU ETA dismiss, etc.) — Z1 leaf-friendly helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import BASE_DIR

_LOCAL_DIR = BASE_DIR / "config" / "local"
_FLAGS_PATH = _LOCAL_DIR / "ui_flags.json"


def _read_flags() -> dict[str, Any]:
    try:
        if _FLAGS_PATH.is_file():
            data = json.loads(_FLAGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return {}


def _write_flags(data: dict[str, Any]) -> None:
    _LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    _FLAGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sam3_cpu_eta_dismissed() -> bool:
    return bool(_read_flags().get("sam3_cpu_eta_dismissed"))


def set_sam3_cpu_eta_dismissed(value: bool = True) -> None:
    flags = _read_flags()
    flags["sam3_cpu_eta_dismissed"] = bool(value)
    _write_flags(flags)


def accel_offer_dismissed() -> bool:
    return bool(_read_flags().get("accel_offer_dismissed"))


def set_accel_offer_dismissed(value: bool = True) -> None:
    flags = _read_flags()
    flags["accel_offer_dismissed"] = bool(value)
    _write_flags(flags)
