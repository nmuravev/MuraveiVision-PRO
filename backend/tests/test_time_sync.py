"""P3.15.2: Auto time sync unit tests (no real video)."""
from __future__ import annotations

import unittest
from unittest import mock

from services import time_sync as ts


class SyncGpsTrackTests(unittest.TestCase):
    def test_pairs_within_tolerance(self) -> None:
        before = [
            {"timestamp": 0.0, "lat": 55.0, "lon": 37.0, "alt": 40.0},
            {"timestamp": 1.0, "lat": 55.00001, "lon": 37.00001, "alt": 40.0},
            {"timestamp": 2.0, "lat": 55.00002, "lon": 37.00002, "alt": 41.0},
            {"timestamp": 3.0, "lat": 55.00003, "lon": 37.00003, "alt": 41.0},
            {"timestamp": 4.0, "lat": 55.00004, "lon": 37.00004, "alt": 42.0},
            {"timestamp": 5.0, "lat": 55.00005, "lon": 37.00005, "alt": 42.0},
        ]
        # Same path, time offset +2s
        after = [
            {"timestamp": t + 2.0, "lat": p["lat"], "lon": p["lon"], "alt": p["alt"]}
            for t, p in zip([0, 1, 2, 3, 4, 5], before)
        ]
        out = ts.sync_by_gps_track(before, after, tolerance_m=15.0)
        self.assertEqual(out["method"], "gps")
        self.assertGreaterEqual(len(out["pairs"]), 5)
        for pair in out["pairs"]:
            self.assertLessEqual(pair["distance_m"], 15.0)
            self.assertAlmostEqual(pair["time_after"] - pair["time_before"], 2.0, delta=0.5)
        self.assertGreaterEqual(len(out["segments"]), 1)


class SyncDetectionsTests(unittest.TestCase):
    def test_same_class_close_centers(self) -> None:
        before = [
            {
                "time_sec": 10.0,
                "class_name": "trench",
                "bbox_x": 0.4,
                "bbox_y": 0.4,
                "bbox_w": 0.1,
                "bbox_h": 0.1,
                "confidence": 0.9,
            }
        ]
        after = [
            {
                "time_sec": 7.0,
                "class_name": "trench",
                "bbox_x": 0.41,
                "bbox_y": 0.42,
                "bbox_w": 0.1,
                "bbox_h": 0.1,
                "confidence": 0.8,
            },
            {
                "time_sec": 8.0,
                "class_name": "person",
                "bbox_x": 0.1,
                "bbox_y": 0.1,
                "bbox_w": 0.1,
                "bbox_h": 0.1,
                "confidence": 0.7,
            },
        ]
        out = ts.sync_by_detections(before, after, class_tolerance=0.15)
        self.assertEqual(out["method"], "detections")
        self.assertEqual(len(out["pairs"]), 1)
        self.assertEqual(out["pairs"][0]["class_name"], "trench")
        self.assertEqual(out["pairs"][0]["time_before"], 10.0)
        self.assertEqual(out["pairs"][0]["time_after"], 7.0)


class GroupSegmentsTests(unittest.TestCase):
    def test_merge_and_split(self) -> None:
        pairs = [
            {"time_before": 0.0, "time_after": 2.0},
            {"time_before": 1.0, "time_after": 3.0},
            {"time_before": 1.5, "time_after": 3.5},
            {"time_before": 10.0, "time_after": 12.0},
            {"time_before": 11.0, "time_after": 13.0},
        ]
        segs = ts.group_into_segments(pairs, max_gap_sec=2.0)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0]["pair_count"], 3)
        self.assertEqual(segs[0]["start_before"], 0.0)
        self.assertEqual(segs[0]["end_before"], 1.5)
        self.assertEqual(segs[1]["pair_count"], 2)
        self.assertEqual(segs[1]["start_before"], 10.0)


class AutoSyncFallbackTests(unittest.TestCase):
    @mock.patch("services.time_sync._load_detections")
    @mock.patch("services.time_sync._load_track_points")
    @mock.patch("services.time_sync._resolve_source_keys")
    def test_empty_tracks_falls_back_to_detections(
        self,
        mock_keys: mock.MagicMock,
        mock_track: mock.MagicMock,
        mock_list: mock.MagicMock,
    ) -> None:
        mock_keys.return_value = ("a.mp4", "b.mp4")
        mock_track.return_value = []
        mock_list.side_effect = [
            [
                {
                    "time_sec": 5.0,
                    "class_name": "trench",
                    "bbox_x": 0.4,
                    "bbox_y": 0.4,
                    "bbox_w": 0.1,
                    "bbox_h": 0.1,
                    "confidence": 0.9,
                }
            ],
            [
                {
                    "time_sec": 3.0,
                    "class_name": "trench",
                    "bbox_x": 0.41,
                    "bbox_y": 0.41,
                    "bbox_w": 0.1,
                    "bbox_h": 0.1,
                    "confidence": 0.85,
                }
            ],
        ]
        out = ts.auto_sync("a.mp4", "b.mp4", source="auto")
        self.assertEqual(out["method_used"], "detections")
        self.assertGreaterEqual(out["pair_count_total"], 1)
        self.assertIsNotNone(out["message"])


if __name__ == "__main__":
    unittest.main()
