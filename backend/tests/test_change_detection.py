"""P3.15 v1: change detection unit tests (no real video)."""
from __future__ import annotations

import math
import unittest

import cv2
import numpy as np

from services import change_detection as cd


def _det(
    det_id: str,
    cls: str,
    lat: float | None,
    lon: float | None,
    time_sec: float = 10.0,
) -> dict:
    return {
        "id": det_id,
        "class_name": cls,
        "time_sec": time_sec,
        "bbox_x": 0.1,
        "bbox_y": 0.1,
        "bbox_w": 0.2,
        "bbox_h": 0.2,
        "confidence": 0.9,
        "gps_lat": lat,
        "gps_lon": lon,
    }


class HaversineTests(unittest.TestCase):
    def test_known_distance(self) -> None:
        # ~111 km per degree latitude at equator
        d = cd.haversine_m(0.0, 0.0, 1.0, 0.0)
        self.assertGreater(d, 110_000)
        self.assertLess(d, 112_000)

    def test_zero_distance(self) -> None:
        self.assertAlmostEqual(cd.haversine_m(55.0, 37.0, 55.0, 37.0), 0.0, places=3)


class FilterDetectionsTests(unittest.TestCase):
    def test_window(self) -> None:
        dets = [_det("a", "trench", 1.0, 1.0, 10.0), _det("b", "trench", 1.0, 1.0, 12.0)]
        out = cd.filter_detections_at_time(dets, 10.5, 0.5)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "a")


class AlignGpsTests(unittest.TestCase):
    def test_stable_match(self) -> None:
        before = [_det("b1", "trench", 55.0, 37.0)]
        after = [_det("a1", "trench", 55.00001, 37.00001)]
        matches, new, removed = cd.align_by_gps(before, after, tolerance_m=10, moved_m=3)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["status"], "stable")
        self.assertEqual(new, [])
        self.assertEqual(removed, [])

    def test_moved_vs_new_removed(self) -> None:
        before = [_det("b1", "trench", 55.0, 37.0), _det("b2", "person", 55.0, 37.01)]
        after = [_det("a1", "trench", 55.00005, 37.00005), _det("a2", "car", 55.0, 37.02)]
        matches, new, removed = cd.align_by_gps(before, after, tolerance_m=10, moved_m=3)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["status"], "moved")
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]["id"], "a2")
        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0]["id"], "b2")

    def test_class_mismatch_no_match(self) -> None:
        before = [_det("b1", "trench", 55.0, 37.0)]
        after = [_det("a1", "person", 55.0, 37.0)]
        matches, new, removed = cd.align_by_gps(before, after)
        self.assertEqual(matches, [])
        self.assertEqual(len(new), 1)
        self.assertEqual(len(removed), 1)


class DiffMaskTests(unittest.TestCase):
    def test_white_square_on_black(self) -> None:
        engine = cd.ChangeDetectionEngine()
        before = np.zeros((100, 100, 3), dtype=np.uint8)
        after = before.copy()
        after[20:40, 20:40] = 255
        result = engine.compute_diff_mask(before, after, None, threshold=30)
        regions = result["regions"]
        self.assertGreaterEqual(len(regions), 1)
        kinds = {r["kind"] for r in regions}
        self.assertIn("new", kinds)

    def test_compute_diff_mask_returns_heatmap(self) -> None:
        import base64

        engine = cd.ChangeDetectionEngine()
        before = np.zeros((100, 100, 3), dtype=np.uint8)
        after = before.copy()
        after[20:40, 20:40] = 255
        result = engine.compute_diff_mask(before, after, None, threshold=30)
        self.assertIn("heatmap_b64", result)
        b64 = result["heatmap_b64"]
        self.assertTrue(isinstance(b64, str) and len(b64) > 0)
        self.assertTrue(b64.startswith("iVBOR"))
        raw = base64.b64decode(b64)
        arr = np.frombuffer(raw, dtype=np.uint8)
        decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded.shape[0], 100)
        self.assertEqual(decoded.shape[1], 100)


class AlignFeaturesTests(unittest.TestCase):
    def test_checkerboard_shift(self) -> None:
        engine = cd.ChangeDetectionEngine()
        size = 200
        before = np.zeros((size, size, 3), dtype=np.uint8)
        after = np.zeros((size, size, 3), dtype=np.uint8)
        for y in range(0, size, 20):
            for x in range(0, size, 20):
                if ((x // 20) + (y // 20)) % 2 == 0:
                    before[y : y + 20, x : x + 20] = (200, 200, 200)
        # shift by 5 px
        after[5:size, 5:size] = before[0 : size - 5, 0 : size - 5]
        H, ratio = engine.align_by_features(before, after)
        self.assertIsNotNone(H)
        assert H is not None
        self.assertEqual(H.shape, (3, 3))
        self.assertGreater(ratio, 0.15)


if __name__ == "__main__":
    unittest.main()
