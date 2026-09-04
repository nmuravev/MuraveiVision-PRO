"""Batch scan segment bounds (t_start/t_end)."""
from __future__ import annotations

import unittest


class TestBatchScanSegmentMath(unittest.TestCase):
    def test_segment_frame_bounds(self) -> None:
        fps = 30.0
        total = 1530  # 51s
        t_start = 10.0
        t_end = 20.0
        start_frame = int(t_start * fps)
        end_frame = int(t_end * fps)
        self.assertEqual(start_frame, 300)
        self.assertEqual(end_frame, 600)
        frame_step = 30  # 1 fps
        span = end_frame - start_frame + 1
        sample_total = max(1, (span + frame_step - 1) // frame_step)
        self.assertEqual(sample_total, 11)


if __name__ == "__main__":
    unittest.main()
