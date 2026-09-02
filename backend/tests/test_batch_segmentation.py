"""Unit tests for P3.13.2 batch segmentation (mocked engine + VideoCapture)."""
from __future__ import annotations

import time
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from services import batch_segmentation as bs


class _FakeCap:
    def __init__(self, frames: int = 90, fps: float = 30.0) -> None:
        self._frames = frames
        self._fps = fps
        self._pos = 0
        self._opened = True

    def isOpened(self) -> bool:
        return self._opened

    def get(self, prop: int) -> float:
        import cv2

        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return float(self._frames)
        if prop == cv2.CAP_PROP_FPS:
            return float(self._fps)
        return 0.0

    def set(self, prop: int, value: float) -> bool:
        self._pos = int(value)
        return True

    def read(self):
        if self._pos >= self._frames:
            return False, None
        frame = np.zeros((16, 16, 3), dtype=np.uint8)
        frame[:] = (30, 60, 90)
        self._pos += 1
        return True, frame

    def release(self) -> None:
        self._opened = False


class BatchSegmentationTests(unittest.TestCase):
    def setUp(self) -> None:
        # Reset module state between tests
        with bs._lock:
            bs._abort.clear()
            bs._thread = None
            bs._state.update(
                {
                    "task_id": None,
                    "status": "idle",
                    "progress": 0.0,
                    "processed": 0,
                    "sample_total": 0,
                    "mask_total": 0,
                    "message": "",
                    "error": None,
                    "video_path": None,
                    "frame_step": 30,
                    "confidence": 0.5,
                    "results": [],
                    "owned_load": False,
                }
            )

    def _wait_terminal(self, task_id: str, timeout: float = 5.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = bs.status(task_id)
            if st["status"] in ("done", "error", "aborted"):
                return st
            time.sleep(0.02)
        self.fail(f"batch did not finish: {bs.status(task_id)}")

    def test_batch_seg_processes_frames(self) -> None:
        engine = mock.MagicMock()
        engine.status.return_value = {"loaded": True, "ready": True}
        engine.infer_jpeg.return_value = {
            "masks": [{"class": "trench", "conf": 0.9, "polygon_norm": [[0.1, 0.1], [0.2, 0.1], [0.15, 0.2]]}],
            "ms": 1,
        }

        with (
            mock.patch.object(bs, "get_seg_engine", return_value=engine),
            mock.patch.object(bs, "_resolve_video", return_value=(Path("archive/clip.mp4"), "archive/clip.mp4")),
            mock.patch.object(bs.cv2, "VideoCapture", return_value=_FakeCap(90, 30.0)),
        ):
            started = bs.start(video_path="archive/clip.mp4", frame_step=30, confidence=0.5)
            task_id = started["task_id"]
            self.assertEqual(started["status"], "running")
            st = self._wait_terminal(task_id)
            self.assertEqual(st["status"], "done")
            # 90 frames / step 30 → 3 samples
            self.assertEqual(st["processed"], 3)
            self.assertEqual(len(st["results"]), 3)
            self.assertEqual(st["mask_total"], 3)
            engine.unload_model.assert_not_called()

    def test_batch_seg_abort(self) -> None:
        engine = mock.MagicMock()
        engine.status.return_value = {"loaded": True, "ready": True}

        def slow_infer(*_a, **_k):
            time.sleep(0.05)
            return {"masks": [], "ms": 1}

        engine.infer_jpeg.side_effect = slow_infer

        with (
            mock.patch.object(bs, "get_seg_engine", return_value=engine),
            mock.patch.object(bs, "_resolve_video", return_value=(Path("archive/clip.mp4"), "archive/clip.mp4")),
            mock.patch.object(bs.cv2, "VideoCapture", return_value=_FakeCap(3000, 30.0)),
        ):
            started = bs.start(video_path="archive/clip.mp4", frame_step=1, confidence=0.5)
            task_id = started["task_id"]
            time.sleep(0.08)
            aborted = bs.abort(task_id)
            self.assertIn(aborted["status"], ("aborted", "done"))
            # Prefer aborted when stop was requested mid-run
            st = self._wait_terminal(task_id)
            self.assertIn(st["status"], ("aborted", "done"))

    def test_batch_seg_unloads_model_when_owned(self) -> None:
        engine = mock.MagicMock()
        engine.status.return_value = {"loaded": False, "ready": True}
        engine.infer_jpeg.return_value = {"masks": [], "ms": 1}

        with (
            mock.patch.object(bs, "get_seg_engine", return_value=engine),
            mock.patch.object(bs, "_resolve_video", return_value=(Path("archive/clip.mp4"), "archive/clip.mp4")),
            mock.patch.object(bs.cv2, "VideoCapture", return_value=_FakeCap(60, 30.0)),
        ):
            started = bs.start(video_path="archive/clip.mp4", frame_step=30, confidence=0.5)
            st = self._wait_terminal(started["task_id"])
            self.assertEqual(st["status"], "done")
            engine.load_model.assert_called()
            engine.unload_model.assert_called()


if __name__ == "__main__":
    unittest.main()
