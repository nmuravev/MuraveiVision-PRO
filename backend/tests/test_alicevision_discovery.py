"""Unit tests for AliceVision sidecar discovery."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import alicevision


class TestAliceVisionDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        alicevision.clear_caches()
        self._old_env = os.environ.get("ALICEVISION_ROOT")
        if "ALICEVISION_ROOT" in os.environ:
            del os.environ["ALICEVISION_ROOT"]

    def tearDown(self) -> None:
        alicevision.clear_caches()
        if self._old_env is None:
            os.environ.pop("ALICEVISION_ROOT", None)
        else:
            os.environ["ALICEVISION_ROOT"] = self._old_env

    def test_missing_sidecar_returns_false(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            fake_base = Path(td)
            with patch.object(alicevision, "BASE_DIR", fake_base):
                with patch.object(alicevision, "_SIDECAR", fake_base / "sidecars" / "alicevision"):
                    with patch.object(alicevision, "_MANIFEST", fake_base / "missing.json"):
                        self.assertIsNone(alicevision.alicevision_root())
                        self.assertFalse(alicevision.alicevision_available())
                        self.assertIsNone(alicevision.alicevision_version())

    def test_env_override_resolves_bin(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "av"
            bin_dir = root / "bin"
            bin_dir.mkdir(parents=True)
            tool = "aliceVision_prepareDenseScene.exe" if sys.platform.startswith("win") else "aliceVision_prepareDenseScene"
            (bin_dir / tool).write_bytes(b"")
            os.environ["ALICEVISION_ROOT"] = str(root)
            alicevision.clear_caches()
            self.assertEqual(alicevision.alicevision_root(), root.resolve())
            self.assertTrue(alicevision.alicevision_available())
            path = alicevision.alicevision_bin("prepareDenseScene")
            self.assertTrue(path.name.startswith("aliceVision_prepareDenseScene"))

    def test_sidecar_layout_under_base(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            plat = alicevision._platform_dir_name()
            bin_dir = base / "sidecars" / "alicevision" / plat / "bin"
            bin_dir.mkdir(parents=True)
            tool = "aliceVision_prepareDenseScene.exe" if sys.platform.startswith("win") else "aliceVision_prepareDenseScene"
            (bin_dir / tool).write_bytes(b"")
            man = base / "scripts" / "alicevision_manifest.json"
            man.parent.mkdir(parents=True)
            man.write_text(json.dumps({"chosen": {"version": "3.3.0"}}), encoding="utf-8")
            with patch.object(alicevision, "BASE_DIR", base):
                with patch.object(alicevision, "_SIDECAR", base / "sidecars" / "alicevision"):
                    with patch.object(alicevision, "_MANIFEST", man):
                        alicevision.clear_caches()
                        self.assertTrue(alicevision.alicevision_available())
                        self.assertEqual(alicevision.alicevision_version(), "3.3.0")
                        self.assertIn("ALICEVISION_ROOT", alicevision.alicevision_env())

    def test_bin_missing_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "bin").mkdir()
            os.environ["ALICEVISION_ROOT"] = str(root)
            alicevision.clear_caches()
            with self.assertRaises(FileNotFoundError):
                alicevision.alicevision_bin("meshing")


if __name__ == "__main__":
    unittest.main()
