"""Smoke: recon layout paths (no GPU/COLMAP required)."""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "backend"))

from services.recon_scanner import RECON_ROOT, _job_dir  # noqa: E402


def main() -> int:
    RECON_ROOT.mkdir(parents=True, exist_ok=True)
    test_id = "smoke_layout"
    jd = _job_dir(test_id)
    jd.mkdir(parents=True, exist_ok=True)
    (jd / "frames").mkdir(exist_ok=True)
    assert RECON_ROOT.is_dir()
    assert jd.is_dir()
    print(f"OK recon root={RECON_ROOT}")
    print(f"OK job dir={jd}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
