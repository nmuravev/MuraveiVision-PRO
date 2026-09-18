"""Leaf path/version constants — no imports from main/api/services."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# BASE_DIR for .exe and .py (same logic previously in main.py)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

DIST_DIR = BASE_DIR / "dist"
MODELS_DIR = BASE_DIR / "assets" / "models"
SAM3_WEIGHT_NAME = "sam3.pt"
SAM3_WEIGHT_PATH = MODELS_DIR / SAM3_WEIGHT_NAME

# Tactical detect priority (best available). Never COCO stock s/m/l.
TACTICAL_WEIGHT_LADDER: tuple[str, ...] = (
    "yolo26l-ft.pt",
    "yolo26m-ft.pt",
    "yolo26s-ft.pt",
    "yolo26n-ft.pt",
    "yolo26n.pt",
)

# Unified engine status vocabulary (API/UI one source).
ENGINE_STATUS_OFFLINE = "offline"
ENGINE_STATUS_CPU = "cpu"
ENGINE_STATUS_DIRECTML = "directml"
ENGINE_STATUS_CUDA = "cuda"

# Default timeout for Ollama AI requests (seconds)
GENERATE_TIMEOUT = 60.0


def _read_app_version() -> str:
    """Single source: pack/repo VERSION file → package.json → unknown."""
    ver_file = BASE_DIR / "VERSION"
    try:
        if ver_file.is_file():
            text = ver_file.read_text(encoding="utf-8").strip().splitlines()
            if text and text[0].strip():
                return text[0].strip().lstrip("vV")
    except OSError:
        pass
    pkg = BASE_DIR / "package.json"
    try:
        if pkg.is_file():
            data = json.loads(pkg.read_text(encoding="utf-8"))
            v = str(data.get("version") or "").strip()
            if v:
                return v.lstrip("vV")
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return "unknown"


def read_kit() -> str:
    """Pack self-id: KIT file at pack root → mini|full; else env; else dev."""
    kit_file = BASE_DIR / "KIT"
    try:
        if kit_file.is_file():
            raw = kit_file.read_text(encoding="utf-8").strip().lower()
            if raw in ("mini", "full"):
                return raw
    except OSError:
        pass
    import os

    env = (os.environ.get("MURAVEI_BUILD_PROFILE") or "").strip().lower()
    if env in ("mini", "full"):
        return env
    if env in ("fullkit", "full_kit"):
        return "full"
    return "dev"


def resolve_default_detect_weight(models_dir: Path | None = None) -> Path | None:
    """First existing tactical weight on the locked ladder under assets/models."""
    root = models_dir or MODELS_DIR
    for name in TACTICAL_WEIGHT_LADDER:
        path = root / name
        try:
            if path.is_file() and path.stat().st_size > 1024:
                return path
        except OSError:
            continue
    return None


APP_VERSION = _read_app_version()
