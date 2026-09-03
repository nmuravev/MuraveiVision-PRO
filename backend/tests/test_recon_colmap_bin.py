"""COLMAP sidecar auto-detection for recon_scanner."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from services import recon_scanner


class TestColmapBin(unittest.TestCase):
    def test_sidecar_fallback_without_env(self) -> None:
        sidecar = recon_scanner.BASE_DIR / "sidecars" / "colmap"
        if not sidecar.is_dir():
            self.skipTest("sidecars/colmap not installed")
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("COLMAP_ROOT", None)
            found = recon_scanner._colmap_bin()
        self.assertIsNotNone(found)
        self.assertTrue(Path(found).is_file())

    def test_env_root_takes_precedence(self) -> None:
        sidecar = recon_scanner.BASE_DIR / "sidecars" / "colmap"
        if not sidecar.is_dir():
            self.skipTest("sidecars/colmap not installed")
        with patch.dict(os.environ, {"COLMAP_ROOT": str(sidecar)}, clear=False):
            found = recon_scanner._colmap_bin()
        self.assertIsNotNone(found)
        self.assertTrue(str(found).startswith(str(sidecar)))


if __name__ == "__main__":
    unittest.main()
