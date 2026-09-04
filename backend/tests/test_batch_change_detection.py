"""Unit tests for P3.15.5 batch change detection (mocked sync + analyze)."""
from __future__ import annotations

import time
import unittest
from unittest import mock

from services import batch_change_detection as bcd
from services.change_export import build_batch_change_html


def _fake_analyze(**kwargs):  # noqa: ANN003
    tb = float(kwargs.get("time_before") or 0)
    return {
        "method": "gps",
        "aligned": True,
        "message": None,
        "summary": {
            "total_before": 2,
            "total_after": 2,
            "matched": 1,
            "stable": 0,
            "moved": 1,
            "new": 1,
            "removed": 1,
        },
        "matches": [
            {
                "before_id": f"b-{tb}",
                "after_id": f"a-{tb}",
                "class_name": "tank",
                "distance_m": 5.0,
                "status": "moved",
                "before_bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2},
                "after_bbox": {"x1": 0.15, "y1": 0.15, "x2": 0.25, "y2": 0.25},
            }
        ],
        "new": [{"id": f"n-{tb}", "class_name": "person", "bbox": {}, "confidence": 0.9}],
        "removed": [{"id": "r-shared", "class_name": "car", "bbox": {}, "confidence": 0.8}],
        "image_diff": {"inlier_ratio": 0.5, "regions": [], "heatmap_b64": "AAAA"},
    }


class BatchChangeDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        with bcd._lock:
            bcd._abort.clear()
            bcd._thread = None
            bcd._state.update(
                {
                    "task_id": None,
                    "status": "idle",
                    "progress": 0.0,
                    "processed": 0,
                    "sample_total": 0,
                    "message": "",
                    "error": None,
                    "video_before": None,
                    "video_after": None,
                    "source": "auto",
                    "pair_stride": 1,
                    "max_pairs": 50,
                    "use_image_fallback": False,
                    "tolerance_m": 10.0,
                    "moved_m": 3.0,
                    "time_window_sec": 0.5,
                    "sync_method": None,
                    "pair_count_total": 0,
                    "results": [],
                    "aggregate": None,
                }
            )

    def _wait_terminal(self, task_id: str, timeout: float = 5.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = bcd.status(task_id)
            if st["status"] in ("done", "error", "aborted"):
                return st
            time.sleep(0.02)
        self.fail(f"batch CD did not finish: {bcd.status(task_id)}")

    def test_processes_pairs_and_strips_heatmap(self) -> None:
        pairs = [
            {"time_before": 1.0, "time_after": 2.0},
            {"time_before": 3.0, "time_after": 4.0},
            {"time_before": 5.0, "time_after": 6.0},
        ]
        sync = {
            "method_used": "gps",
            "pairs": pairs,
            "segments": [],
            "message": None,
            "pair_count_total": 3,
        }
        with (
            mock.patch("services.time_sync.auto_sync", return_value=sync),
            mock.patch("services.change_detection.analyze_pair", side_effect=_fake_analyze),
        ):
            started = bcd.start(
                video_before="a.mp4",
                video_after="b.mp4",
                pair_stride=1,
                max_pairs=50,
            )
            task_id = started["task_id"]
            self.assertEqual(started["status"], "running")
            st = self._wait_terminal(task_id)
        self.assertEqual(st["status"], "done")
        self.assertEqual(st["processed"], 3)
        self.assertEqual(len(st["results"]), 3)
        for row in st["results"]:
            diff = row.get("image_diff") or {}
            self.assertNotIn("heatmap_b64", diff)
        agg = st["aggregate"]
        self.assertEqual(agg["pair_count"], 3)
        self.assertEqual(agg["unique_removed"], 1)  # r-shared deduped
        self.assertEqual(agg["sum_removed"], 3)
        self.assertEqual(agg["unique_new"], 3)

    def test_pair_stride_and_max_pairs(self) -> None:
        pairs = [{"time_before": float(i), "time_after": float(i)} for i in range(10)]
        sync = {
            "method_used": "detections",
            "pairs": pairs,
            "pair_count_total": 10,
            "segments": [],
            "message": None,
        }
        with (
            mock.patch("services.time_sync.auto_sync", return_value=sync),
            mock.patch("services.change_detection.analyze_pair", side_effect=_fake_analyze),
        ):
            started = bcd.start(
                video_before="a.mp4",
                video_after="b.mp4",
                pair_stride=2,
                max_pairs=3,
            )
            st = self._wait_terminal(started["task_id"])
        self.assertEqual(st["status"], "done")
        self.assertEqual(st["sample_total"], 3)
        self.assertEqual(st["processed"], 3)

    def test_empty_pairs_done(self) -> None:
        sync = {
            "method_used": "none",
            "pairs": [],
            "pair_count_total": 0,
            "segments": [],
            "message": "нет пар",
        }
        with mock.patch("services.time_sync.auto_sync", return_value=sync):
            started = bcd.start(video_before="a.mp4", video_after="b.mp4")
            st = self._wait_terminal(started["task_id"])
        self.assertEqual(st["status"], "done")
        self.assertEqual(st["processed"], 0)
        self.assertIn("нет пар", (st["message"] or "").lower())

    def test_second_start_raises(self) -> None:
        def _slow_sync(*_a, **_k):  # noqa: ANN002, ANN003
            time.sleep(0.3)
            return {
                "method_used": "gps",
                "pairs": [{"time_before": 1.0, "time_after": 1.0}],
                "pair_count_total": 1,
                "segments": [],
                "message": None,
            }

        with (
            mock.patch("services.time_sync.auto_sync", side_effect=_slow_sync),
            mock.patch("services.change_detection.analyze_pair", side_effect=_fake_analyze),
        ):
            first = bcd.start(video_before="a.mp4", video_after="b.mp4")
            with self.assertRaises(RuntimeError):
                bcd.start(video_before="a.mp4", video_after="b.mp4")
            self._wait_terminal(first["task_id"])

    def test_abort(self) -> None:
        def _slow_analyze(**kwargs):  # noqa: ANN003
            time.sleep(0.15)
            return _fake_analyze(**kwargs)

        pairs = [{"time_before": float(i), "time_after": float(i)} for i in range(20)]
        sync = {
            "method_used": "gps",
            "pairs": pairs,
            "pair_count_total": 20,
            "segments": [],
            "message": None,
        }
        with (
            mock.patch("services.time_sync.auto_sync", return_value=sync),
            mock.patch("services.change_detection.analyze_pair", side_effect=_slow_analyze),
        ):
            started = bcd.start(video_before="a.mp4", video_after="b.mp4", max_pairs=20)
            task_id = started["task_id"]
            time.sleep(0.05)
            aborted = bcd.abort(task_id)
        self.assertIn(aborted["status"], ("aborted", "done"))
        if aborted["status"] == "aborted":
            self.assertLess(aborted["processed"], 20)

    def test_build_aggregate_unique(self) -> None:
        rows = [
            {
                "summary": {"new": 1, "removed": 1, "moved": 1, "stable": 0, "matched": 1},
                "new": [{"id": "n1"}],
                "removed": [{"id": "r1"}],
                "matches": [{"status": "moved", "before_id": "b1", "after_id": "a1"}],
            },
            {
                "summary": {"new": 1, "removed": 1, "moved": 1, "stable": 0, "matched": 1},
                "new": [{"id": "n1"}],
                "removed": [{"id": "r2"}],
                "matches": [{"status": "moved", "before_id": "b1", "after_id": "a1"}],
            },
        ]
        agg = bcd.build_aggregate(rows, sync_method="gps")
        self.assertEqual(agg["unique_new"], 1)
        self.assertEqual(agg["unique_removed"], 2)
        self.assertEqual(agg["unique_moved"], 1)
        self.assertEqual(agg["sum_new"], 2)

    def test_batch_html_contains_pairs(self) -> None:
        html = build_batch_change_html(
            {"pair_count": 1, "unique_new": 1, "unique_removed": 0, "unique_moved": 0,
             "sum_new": 1, "sum_removed": 0, "sum_moved": 0, "sync_method": "gps"},
            [
                {
                    "time_before": 12.5,
                    "time_after": 8.0,
                    "method": "gps",
                    "summary": {"new": 1, "removed": 0, "moved": 0, "stable": 0},
                }
            ],
            {"video_before": "a.mp4", "video_after": "b.mp4", "generated_at": "t"},
        )
        self.assertIn("Пакетный отчёт", html)
        self.assertIn("12.5", html)
        self.assertIn("a.mp4", html)


if __name__ == "__main__":
    unittest.main()
