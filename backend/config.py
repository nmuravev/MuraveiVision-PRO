"""Leaf path constants — no imports from main/api/services (avoids circular imports)."""
from __future__ import annotations

import sys
from pathlib import Path

# BASE_DIR for .exe and .py (same logic previously in main.py)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

DIST_DIR = BASE_DIR / "dist"
