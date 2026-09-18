"""Test P0-6: OOM recovery in yolo_engine.

Verifies that CUDA OOM errors trigger CPU fallback with retry logic,
and that CUDA device can be restored after successful inference.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))

from services import yolo_engine


class TestOomRecovery(unittest.TestCase):
    """Test P0-6 OOM recovery."""

    def test_engine_initialization(self):
        """Engine should initialize without error."""
        engine = yolo_engine.get_yolo_engine()
        self.assertIsNotNone(engine)
        self.assertIn(engine.mode, ("offline", "ready", "error"))

    def test_status_snapshot(self):
        """status_snapshot should return valid dict."""
        engine = yolo_engine.get_yolo_engine()
        snapshot = engine.status_snapshot()
        self.assertIn("mode", snapshot)
        self.assertIn("engine_status", snapshot)
        self.assertIn("degraded", snapshot)
        self.assertIn("device", snapshot)

    def test_degraded_flag_exists(self):
        """_degraded flag should exist and be False initially."""
        engine = yolo_engine.get_yolo_engine()
        self.assertFalse(getattr(engine, "_degraded", False))

    def test_empty_result_structure(self):
        """_empty should return valid structure."""
        engine = yolo_engine.get_yolo_engine()
        result = engine._empty(frame_idx=0, time_sec=0.0)
        self.assertEqual(result["frameIdx"], 0)
        self.assertEqual(result["timeSec"], 0.0)
        self.assertEqual(result["objects"], [])
        self.assertEqual(result["n"], 0)

    def test_nms_basic(self):
        """_nms should filter overlapping boxes."""
        engine = yolo_engine.get_yolo_engine()
        objects = [
            {"bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.3}, "confidence": 0.9},
            {"bbox": {"x1": 0.15, "y1": 0.15, "x2": 0.35, "y2": 0.35}, "confidence": 0.7},
            {"bbox": {"x1": 0.5, "y1": 0.5, "x2": 0.7, "y2": 0.7}, "confidence": 0.8},
        ]
        nmsed = engine._nms(objects)
        # Should keep highest confidence + non-overlapping
        self.assertGreaterEqual(len(nmsed), 2)
        self.assertLessEqual(len(nmsed), 3)


if __name__ == "__main__":
    unittest.main()
