"""Train presets loader (config/train_presets.json)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import train_presets


class TestTrainPresets(unittest.TestCase):
    def test_builtin_fallback(self) -> None:
        with patch.object(train_presets, "PRESETS_PATH", Path("/nonexistent/train_presets.json")):
            presets, from_file = train_presets.load_presets()
        self.assertFalse(from_file)
        self.assertIn("balanced", presets)
        self.assertEqual(presets["balanced"]["max_steps"], 7000)

    def test_valid_file(self) -> None:
        raw = {
            "bootstrap": {"label": "B", "script": "bootstrap", "max_points": 1000, "eta": "1s"},
            "balanced": {
                "label": "Bal",
                "script": "gsplat",
                "max_steps": 500,
                "data_factor": 4,
                "eta": "1m",
                "default": True,
            },
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "train_presets.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with patch.object(train_presets, "PRESETS_PATH", path):
                presets, from_file = train_presets.load_presets()
        self.assertTrue(from_file)
        self.assertEqual(presets["balanced"]["max_steps"], 500)

    def test_invalid_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "train_presets.json"
            path.write_text("{not json", encoding="utf-8")
            with patch.object(train_presets, "PRESETS_PATH", path):
                presets, from_file = train_presets.load_presets()
        self.assertFalse(from_file)
        self.assertIn("balanced", presets)

    def test_client_presets_shape(self) -> None:
        with patch.object(train_presets, "total_vram_gb", return_value=8.0):
            with patch(
                "services.alicevision.alicevision_available",
                return_value=True,
            ):
                with patch(
                    "services.alicevision.alicevision_cuda_ready",
                    return_value=(True, ""),
                ):
                    items = train_presets.presets_for_client()
        ids = [i["id"] for i in items]
        self.assertIn("high", ids)
        self.assertIn("sparse", ids)
        self.assertIn("dense", ids)
        high = next(i for i in items if i["id"] == "high")
        self.assertTrue(high["disabled"])
        self.assertIn("VRAM", high["disabled_reason"])

    def test_dense_disabled_without_alicevision(self) -> None:
        with patch.object(train_presets, "total_vram_gb", return_value=16.0):
            with patch(
                "services.alicevision.alicevision_available",
                return_value=False,
            ):
                with patch(
                    "services.alicevision.alicevision_cuda_ready",
                    return_value=(True, ""),
                ):
                    items = train_presets.presets_for_client()
        dense = next(i for i in items if i["id"] == "dense")
        self.assertTrue(dense["disabled"])
        self.assertIn("AliceVision", dense["disabled_reason"])

    def test_aliases_present(self) -> None:
        presets, from_file = train_presets.load_presets()
        self.assertTrue(from_file or "balanced" in presets)
        self.assertIn("balanced", presets)
        self.assertEqual(presets["balanced"].get("alias_of"), "splat")
        self.assertEqual(presets["bootstrap"].get("alias_of"), "sparse")


if __name__ == "__main__":
    unittest.main()
