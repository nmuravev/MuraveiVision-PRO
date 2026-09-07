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


APP_VERSION = _read_app_version()
