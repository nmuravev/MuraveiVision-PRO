"""Unit tests for hardware_detect tiers + component paths (Z5)."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from services import hardware_detect as hd


class HardwareDetectTests(unittest.TestCase):
    def tearDown(self) -> None:
        for k in (
            "MURAVEI_FORCE_TIER",
            "MURAVEI_FORCE_ACCELERATOR",
            "MURAVEI_SIDECARS_DIR",
            "MURAVEI_FFMPEG_DIR",
            "MURAVEI_PYTHON",
            "COLMAP_ROOT",
            "ALICEVISION_ROOT",
        ):
            os.environ.pop(k, None)

    def test_force_tier(self) -> None:
        os.environ["MURAVEI_FORCE_TIER"] = "1"
        t = hd.classify_tier(cuda=True, ram_gb=32, cores=16)
        self.assertEqual(t["tier"], 1)
        self.assertTrue(t["forced"])

    def test_tier2_cuda_strong(self) -> None:
        t = hd.classify_tier(cuda=True, ram_gb=32, cores=12)
        self.assertEqual(t["tier"], 2)

    def test_tier1_no_cuda_strong(self) -> None:
        t = hd.classify_tier(cuda=False, ram_gb=16, cores=4)
        self.assertEqual(t["tier"], 1)

    def test_tier0_weak(self) -> None:
        t = hd.classify_tier(cuda=False, ram_gb=8, cores=4)
        self.assertEqual(t["tier"], 0)

    def test_colmap_env_override(self) -> None:
        with mock.patch.object(hd, "_repo_path", side_effect=lambda *p: Path("/nope") / Path(*p)):
            os.environ["COLMAP_ROOT"] = str(Path.cwd())
            # without files → absent; just ensure override path is consulted without crash
            out = hd.detect_colmap()
            self.assertIn("present", out)

    def test_mismatch_mini_on_tier2(self) -> None:
        msg = hd._mismatch_message("mini", 2)
        self.assertIsNotNone(msg)
        assert msg is not None
        self.assertEqual(msg["level"], "info")

    def test_mismatch_full_on_tier0(self) -> None:
        msg = hd._mismatch_message("full", 0)
        self.assertIsNotNone(msg)
        assert msg is not None
        self.assertEqual(msg["level"], "warning")

    def test_badge_ru(self) -> None:
        badge = hd._badge_ru("mini", {"tier": 0, "label_ru": "офис"})
        self.assertIn("Mini", badge)
        self.assertIn("tier 0", badge)


if __name__ == "__main__":
    unittest.main()
