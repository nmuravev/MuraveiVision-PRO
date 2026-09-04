"""P3.13.3b: SAM3 short propagate (mocked VideoPredictor + temp clip)."""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

from services import sam3_propagate as prop


class _FakeResult:
    def __init__(self) -> None:
        class _M:
            xyn = [np.array([[0.1, 0.1], [0.4, 0.1], [0.25, 0.4]], dtype=np.float64)]

        self.masks = _M()


class Sam3PropagateTests(unittest.TestCase):
    def setUp(self) -> None:
        with prop._lock:
            prop._abort.clear()
            prop._thread = None
            prop._state.update(
                {
                    "task_id": None,
                    "status": "idle",
                    "progress": 0.0,
                    "processed": 0,
                    "sample_total": 0,
                    "mask_total": 0,
                    "persisted": 0,
                    "message": "",
                    "error": None,
                    "video_path": None,
                    "max_frames": 30,
                    "persist": False,
                    "results": [],
                }
            )
        self._tmp = Path(tempfile.mkdtemp())
        self._video = self._tmp / "clip.mp4"
        self._write_video(self._video, frames=45, fps=30.0, size=(32, 32))

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def _write_video(self, path: Path, frames: int, fps: float, size: tuple[int, int]) -> None:
        w, h = size
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
        for i in range(frames):
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            frame[:] = (i % 50, 40, 80)
            writer.write(frame)
        writer.release()

    def _wait(self, task_id: str, timeout: float = 8.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = prop.status(task_id)
            if st["status"] in ("done", "error", "aborted"):
                return st
            time.sleep(0.02)
        self.fail(f"propagate did not finish: {prop.status(task_id)}")

    def test_polygon_aabb_norm(self) -> None:
        aabb = prop.polygon_aabb_norm([[0.2, 0.3], [0.8, 0.3], [0.5, 0.9]])
        assert aabb is not None
        self.assertAlmostEqual(aabb["x1"], 0.2)
        self.assertAlmostEqual(aabb["x2"], 0.8)
        self.assertAlmostEqual(aabb["y1"], 0.3)
        self.assertAlmostEqual(aabb["y2"], 0.9)

    def test_max_frames_clamped(self) -> None:
        engine = mock.MagicMock()
        engine.status.return_value = {"ready": True, "loaded": True, "weight": "sam3.pt"}

        with (
            mock.patch.object(prop, "get_sam3_engine", return_value=engine),
            mock.patch.object(prop, "_resolve_video", return_value=(self._video, "archive/clip.mp4")),
            mock.patch.object(prop, "resolve_named_weight", return_value=self._tmp / "sam3.pt"),
            mock.patch.object(prop, "_unload_yolo_seg"),
            mock.patch.object(
                prop,
                "_run_video_predictor",
                return_value=[_FakeResult() for _ in range(5)],
            ),
        ):
            (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
            started = prop.start(
                video_path="archive/clip.mp4",
                time_sec=0.0,
                max_frames=99,
                bboxes=[{"x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.4}],
                persist=False,
            )
            self.assertEqual(started["max_frames"], 30)
            st = self._wait(started["task_id"])
            self.assertEqual(st["status"], "done")
            self.assertLessEqual(st["processed"], 30)
            self.assertGreater(st["processed"], 0)
            self.assertEqual(st["persisted"], 0)

    def test_persist_inserts_seg_masks(self) -> None:
        engine = mock.MagicMock()
        engine.status.return_value = {"ready": True, "loaded": True, "weight": "sam3.pt"}
        inserted: list = []

        def fake_persist(**kwargs):
            inserted.append(kwargs)
            return 3

        with (
            mock.patch.object(prop, "get_sam3_engine", return_value=engine),
            mock.patch.object(prop, "_resolve_video", return_value=(self._video, "archive/clip.mp4")),
            mock.patch.object(prop, "resolve_named_weight", return_value=self._tmp / "sam3.pt"),
            mock.patch.object(prop, "_unload_yolo_seg"),
            mock.patch.object(
                prop,
                "_run_video_predictor",
                return_value=[_FakeResult() for _ in range(3)],
            ),
            mock.patch.object(prop, "_persist_results", side_effect=fake_persist),
        ):
            (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
            started = prop.start(
                video_path="archive/clip.mp4",
                time_sec=0.0,
                max_frames=3,
                bboxes=[{"x1": 0.1, "y1": 0.1, "x2": 0.5, "y2": 0.5}],
                persist=True,
            )
            st = self._wait(started["task_id"])
            self.assertEqual(st["status"], "done")
            self.assertEqual(len(inserted), 1)
            self.assertEqual(st["persisted"], 3)

    def test_requires_prompts(self) -> None:
        engine = mock.MagicMock()
        engine.status.return_value = {"ready": True, "loaded": True, "weight": "sam3.pt"}
        with mock.patch.object(prop, "get_sam3_engine", return_value=engine):
            with self.assertRaises(ValueError):
                prop.start(video_path="archive/clip.mp4", time_sec=0.0)

    def test_xor_rejects_both_visual_and_text(self) -> None:
        engine = mock.MagicMock()
        engine.status.return_value = {"ready": True, "loaded": True, "weight": "sam3.pt"}
        with mock.patch.object(prop, "get_sam3_engine", return_value=engine):
            with self.assertRaises(ValueError):
                prop.start(
                    video_path="archive/clip.mp4",
                    time_sec=0.0,
                    bboxes=[{"x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}],
                    texts=["trench"],
                )

    def test_text_propagate_uses_semantic(self) -> None:
        engine = mock.MagicMock()
        engine.status.return_value = {"ready": True, "loaded": True, "weight": "sam3.pt"}
        with (
            mock.patch.object(prop, "get_sam3_engine", return_value=engine),
            mock.patch.object(prop, "_resolve_video", return_value=(self._video, "archive/clip.mp4")),
            mock.patch.object(prop, "resolve_named_weight", return_value=self._tmp / "sam3.pt"),
            mock.patch.object(prop, "_unload_yolo_seg"),
            mock.patch.object(
                prop,
                "_run_video_semantic_predictor",
                return_value=[_FakeResult() for _ in range(4)],
            ) as sem,
            mock.patch.object(prop, "_run_video_predictor") as visual,
        ):
            (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
            started = prop.start(
                video_path="archive/clip.mp4",
                time_sec=0.0,
                max_frames=4,
                texts=["trench", "person"],
                persist=False,
            )
            st = self._wait(started["task_id"])
            self.assertEqual(st["status"], "done")
            self.assertGreater(st["processed"], 0)
            sem.assert_called()
            visual.assert_not_called()

    def test_requires_loaded(self) -> None:
        engine = mock.MagicMock()
        engine.status.return_value = {"ready": True, "loaded": False, "weight": "sam3.pt"}
        with mock.patch.object(prop, "get_sam3_engine", return_value=engine):
            with self.assertRaises(RuntimeError):
                prop.start(
                    video_path="archive/clip.mp4",
                    time_sec=0.0,
                    bboxes=[{"x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}],
                )


class SegMasksDbTests(unittest.TestCase):
    def setUp(self) -> None:
        import services.db as db

        self.db = db
        self._prev = db.DB_PATH
        self._tmp = Path(tempfile.mkdtemp())
        db.DB_PATH = self._tmp / "t.db"
        db._initialized = False
        db.init_db()

    def tearDown(self) -> None:
        self.db._initialized = False
        self.db.DB_PATH = self._prev
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_insert_list_soft_delete(self) -> None:
        n = self.db.insert_seg_masks_batch(
            [
                {
                    "source_video": "archive/a.mp4",
                    "time_sec": 1.0,
                    "frame_idx": 30,
                    "polygon_norm": [[0.1, 0.1], [0.2, 0.1], [0.15, 0.2]],
                    "track_id": "trk1",
                },
                {
                    "source_video": "archive/a.mp4",
                    "time_sec": 1.1,
                    "frame_idx": 33,
                    "polygon_norm": [[0.2, 0.2], [0.3, 0.2], [0.25, 0.3]],
                    "track_id": "trk1",
                },
            ]
        )
        self.assertEqual(n, 2)
        rows = self.db.list_seg_masks("archive/a.mp4", track_id="trk1")
        self.assertEqual(len(rows), 2)
        deleted = self.db.soft_delete_seg_masks_by_track("trk1")
        self.assertEqual(deleted, 2)
        self.assertEqual(self.db.list_seg_masks("archive/a.mp4", track_id="trk1"), [])


if __name__ == "__main__":
    unittest.main()
