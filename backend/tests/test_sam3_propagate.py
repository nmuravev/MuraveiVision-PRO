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

    def _wait(self, task_id: str, timeout: float = 15.0) -> dict:
        """Wait for terminal status with deadline. Never infinite-loop."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            st = prop.status(task_id)
            if st["status"] in ("done", "error", "aborted"):
                return st
            time.sleep(0.1)
        self.fail(f"timeout {timeout}s waiting terminal; status={prop.status(task_id)['status']}")

    def _write_video_90(self, path) -> None:
        """Write a 90-frame test video using mov codec (more reliable than mp4v)."""
        w, h = 32, 32
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(path), fourcc, 30.0, (w, h))
        for i in range(90):
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            frame[:] = (i % 50, 40, 80)
            writer.write(frame)
        writer.release()
        # Verify: reopen and count frames
        cap = cv2.VideoCapture(str(path))
        count = 0
        while True:
            ok, _ = cap.read()
            if not ok:
                break
            count += 1
        cap.release()
        if count < 90:
            # mp4v read failed — use a simpler codec
            import os
            os.unlink(path)
            fourcc2 = cv2.VideoWriter_fourcc(*"avc1")
            writer2 = cv2.VideoWriter(str(path), fourcc2, 30.0, (w, h))
            for i in range(90):
                frame = np.zeros((h, w, 3), dtype=np.uint8)
                frame[:] = (i % 50, 40, 80)
                writer2.write(frame)
            writer2.release()

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

    # P3.13.3d: full-video chunking tests (N1 fix: stride=25, last≤30)
    def test_chunking_math_90(self) -> None:
        """90 frames → 4 chunks starts [0,25,50,75] counts [30,30,30,15]."""
        chunks = prop._chunk_video(90)
        self.assertEqual(len(chunks), 4)
        self.assertEqual(chunks, [(0, 30), (25, 30), (50, 30), (75, 15)])

    def test_chunking_math_95(self) -> None:
        """95 frames → 4 chunks starts [0,25,50,75] last=20."""
        chunks = prop._chunk_video(95)
        self.assertEqual(len(chunks), 4)
        self.assertEqual(chunks[-1], (75, 20))

    def test_chunking_math_20(self) -> None:
        """20 frames → 1 chunk [(0, 20)]."""
        chunks = prop._chunk_video(20)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks, [(0, 20)])

    def test_chunking_max_30(self) -> None:
        """Assert no chunk count > WINDOW_SIZE (30)."""
        for total in range(1, 200):
            chunks = prop._chunk_video(total)
            for start, count in chunks:
                self.assertLessEqual(count, prop.WINDOW_SIZE,
                                     f"total={total} chunk ({start},{count}) exceeds 30")

    def test_chunking_coverage(self) -> None:
        """Union of all chunk frames covers 0..total-1 without gaps."""
        for total in [1, 10, 30, 31, 50, 90, 95, 100, 150]:
            chunks = prop._chunk_video(total)
            covered = set()
            for start, count in chunks:
                for i in range(count):
                    covered.add(start + i)
            expected = set(range(total))
            self.assertEqual(covered, expected, f"total={total} coverage gap")

    def test_full_video_propagate(self) -> None:
        """Mock 90-frame video, full_video=True, verify 4 chunks processed."""
        engine = mock.MagicMock()
        engine.status.return_value = {"ready": True, "loaded": True, "weight": "sam3.pt"}
        # Mock cv2.VideoCapture globally to avoid mp4v codec issues
        mock_cap = mock.MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: 90.0 if prop == cv2.CAP_PROP_FRAME_COUNT else 30.0
        mock_cap.read.return_value = (True, np.zeros((32, 32, 3), dtype=np.uint8))
        mock_cap.release.return_value = None
        with (
            mock.patch.object(prop, "get_sam3_engine", return_value=engine),
            mock.patch.object(prop, "_resolve_video", return_value=(self._video, "archive/clip.mp4")),
            mock.patch.object(prop, "resolve_named_weight", return_value=self._tmp / "sam3.pt"),
            mock.patch.object(prop, "_unload_yolo_seg"),
            mock.patch.object(
                prop, "_write_temp_clip",
                return_value=(self._video, 30.0, 32, 32, 30),
            ),
            mock.patch.object(
                prop, "_run_video_predictor",
                return_value=[_FakeResult() for _ in range(30)],
            ),
            mock.patch("cv2.VideoCapture", return_value=mock_cap),
        ):
            (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
            started = prop.start(
                video_path="archive/clip.mp4",
                time_sec=0.0,
                max_frames=30,
                bboxes=[{"x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.4}],
                persist=False,
                full_video=True,
            )
            self.assertTrue(started["full_video"])
            self.assertEqual(started["total_windows"], 4)
            st = self._wait(started["task_id"], timeout=15.0)
            self.assertEqual(st["status"], "done")
            self.assertGreaterEqual(st["processed"], 90)

    def test_abort_mid_chunk_keeps_partial(self) -> None:
        """Abort during chunk 2, verify chunk 1 results kept."""
        engine = mock.MagicMock()
        engine.status.return_value = {"ready": True, "loaded": True, "weight": "sam3.pt"}
        # Mock cv2.VideoCapture globally to avoid mp4v codec issues
        mock_cap = mock.MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: 90.0 if prop == cv2.CAP_PROP_FRAME_COUNT else 30.0
        mock_cap.read.return_value = (True, np.zeros((32, 32, 3), dtype=np.uint8))
        mock_cap.release.return_value = None
        call_count = [0]

        def counting_predictor(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return [_FakeResult() for _ in range(30)]  # chunk 1 completes
            return [_FakeResult() for _ in range(15)]

        with (
            mock.patch.object(prop, "get_sam3_engine", return_value=engine),
            mock.patch.object(prop, "_resolve_video", return_value=(self._video, "archive/clip.mp4")),
            mock.patch.object(prop, "resolve_named_weight", return_value=self._tmp / "sam3.pt"),
            mock.patch.object(prop, "_unload_yolo_seg"),
            mock.patch.object(
                prop, "_write_temp_clip",
                return_value=(self._video, 30.0, 32, 32, 30),
            ),
            mock.patch.object(prop, "_run_video_predictor", side_effect=counting_predictor),
            mock.patch("cv2.VideoCapture", return_value=mock_cap),
        ):
            (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
            started = prop.start(
                video_path="archive/clip.mp4",
                time_sec=0.0,
                max_frames=30,
                bboxes=[{"x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.4}],
                persist=False,
                full_video=True,
            )
            self.assertEqual(started["total_windows"], 4)
            time.sleep(0.5)
            prop.abort(started["task_id"])
            st = self._wait(started["task_id"], timeout=15.0)
            self.assertEqual(st["status"], "aborted")
            self.assertGreater(st["processed"], 0)

    def test_vram_empty_cache_between_chunks(self) -> None:
        """Verify _empty_cache() called between chunks."""
        engine = mock.MagicMock()
        engine.status.return_value = {"ready": True, "loaded": True, "weight": "sam3.pt"}
        # Mock cv2.VideoCapture globally to avoid mp4v codec issues
        mock_cap = mock.MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: 90.0 if prop == cv2.CAP_PROP_FRAME_COUNT else 30.0
        mock_cap.read.return_value = (True, np.zeros((32, 32, 3), dtype=np.uint8))
        mock_cap.release.return_value = None
        with (
            mock.patch.object(prop, "get_sam3_engine", return_value=engine),
            mock.patch.object(prop, "_resolve_video", return_value=(self._video, "archive/clip.mp4")),
            mock.patch.object(prop, "resolve_named_weight", return_value=self._tmp / "sam3.pt"),
            mock.patch.object(prop, "_unload_yolo_seg"),
            mock.patch.object(
                prop, "_write_temp_clip",
                return_value=(self._video, 30.0, 32, 32, 30),
            ),
            mock.patch.object(
                prop, "_run_video_predictor",
                return_value=[_FakeResult() for _ in range(30)],
            ),
            mock.patch.object(prop, "_empty_cache") as mock_cache,
            mock.patch("cv2.VideoCapture", return_value=mock_cap),
        ):
            (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
            started = prop.start(
                video_path="archive/clip.mp4",
                time_sec=0.0,
                max_frames=30,
                bboxes=[{"x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.4}],
                persist=False,
                full_video=True,
            )
            self.assertEqual(started["total_windows"], 4)
            self._wait(started["task_id"], timeout=15.0)
            self.assertGreaterEqual(mock_cache.call_count, 3)

    def test_full_video_default_false(self) -> None:
        """Default max_frames=30 still works (single chunk)."""
        engine = mock.MagicMock()
        engine.status.return_value = {"ready": True, "loaded": True, "weight": "sam3.pt"}
        # Mock _write_temp_clip to avoid mp4v codec read issues
        with (
            mock.patch.object(prop, "get_sam3_engine", return_value=engine),
            mock.patch.object(prop, "_resolve_video", return_value=(self._video, "archive/clip.mp4")),
            mock.patch.object(prop, "resolve_named_weight", return_value=self._tmp / "sam3.pt"),
            mock.patch.object(prop, "_unload_yolo_seg"),
            mock.patch.object(
                prop, "_write_temp_clip",
                return_value=(self._video, 30.0, 32, 32, 5),
            ),
            mock.patch.object(
                prop, "_run_video_predictor",
                return_value=[_FakeResult() for _ in range(5)],
            ),
        ):
            (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
            started = prop.start(
                video_path="archive/clip.mp4",
                time_sec=0.0,
                max_frames=5,
                bboxes=[{"x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.4}],
                persist=False,
                full_video=False,  # explicit default
            )
            self.assertFalse(started["full_video"])
            self.assertEqual(started["total_windows"], 0)
            st = self._wait(started["task_id"])
            self.assertEqual(st["status"], "done")

    def test_persist_full_video(self) -> None:
        """persist=True + full_video=True → verify SQLite insert for all chunks."""
        engine = mock.MagicMock()
        engine.status.return_value = {"ready": True, "loaded": True, "weight": "sam3.pt"}
        inserted: list = []

        def fake_persist(**kwargs):
            inserted.append(kwargs)
            return 3

        # Mock cv2.VideoCapture globally to avoid mp4v codec issues
        mock_cap = mock.MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: 90.0 if prop == cv2.CAP_PROP_FRAME_COUNT else 30.0
        mock_cap.read.return_value = (True, np.zeros((32, 32, 3), dtype=np.uint8))
        mock_cap.release.return_value = None
        with (
            mock.patch.object(prop, "get_sam3_engine", return_value=engine),
            mock.patch.object(prop, "_resolve_video", return_value=(self._video, "archive/clip.mp4")),
            mock.patch.object(prop, "resolve_named_weight", return_value=self._tmp / "sam3.pt"),
            mock.patch.object(prop, "_unload_yolo_seg"),
            mock.patch.object(
                prop, "_write_temp_clip",
                return_value=(self._video, 30.0, 32, 32, 30),
            ),
            mock.patch.object(
                prop, "_run_video_predictor",
                return_value=[_FakeResult() for _ in range(30)],
            ),
            mock.patch.object(prop, "_persist_results", side_effect=fake_persist),
            mock.patch("cv2.VideoCapture", return_value=mock_cap),
        ):
            (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
            started = prop.start(
                video_path="archive/clip.mp4",
                time_sec=0.0,
                max_frames=30,
                bboxes=[{"x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.4}],
                persist=True,
                full_video=True,
            )
            self.assertEqual(started["total_windows"], 4)
            st = self._wait(started["task_id"], timeout=15.0)
            self.assertEqual(st["status"], "done")
            self.assertEqual(len(inserted), 1)

    def test_overlap_dedup_no_duplicate_frames(self) -> None:
        """N3: full_video with overlap → no duplicate frame_idx in results."""
        engine = mock.MagicMock()
        engine.status.return_value = {"ready": True, "loaded": True, "weight": "sam3.pt"}
        # Mock cv2.VideoCapture globally to avoid mp4v codec issues
        mock_cap = mock.MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: 90.0 if prop == cv2.CAP_PROP_FRAME_COUNT else 30.0
        mock_cap.read.return_value = (True, np.zeros((32, 32, 3), dtype=np.uint8))
        mock_cap.release.return_value = None
        with (
            mock.patch.object(prop, "get_sam3_engine", return_value=engine),
            mock.patch.object(prop, "_resolve_video", return_value=(self._video, "archive/clip.mp4")),
            mock.patch.object(prop, "resolve_named_weight", return_value=self._tmp / "sam3.pt"),
            mock.patch.object(prop, "_unload_yolo_seg"),
            mock.patch.object(
                prop, "_write_temp_clip",
                return_value=(self._video, 30.0, 32, 32, 30),
            ),
            mock.patch.object(
                prop, "_run_video_predictor",
                return_value=[_FakeResult() for _ in range(30)],
            ),
            mock.patch("cv2.VideoCapture", return_value=mock_cap),
        ):
            (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
            started = prop.start(
                video_path="archive/clip.mp4",
                time_sec=0.0,
                max_frames=30,
                bboxes=[{"x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.4}],
                persist=False,
                full_video=True,
            )
            self.assertEqual(started["total_windows"], 4)
            st = self._wait(started["task_id"], timeout=15.0)
            self.assertEqual(st["status"], "done")
            frame_indices = [r["frame_idx"] for r in st["results"]]
            self.assertEqual(len(frame_indices), len(set(frame_indices)),
                             "Duplicate frame_idx found in results")

    def test_oom_graceful_error(self) -> None:
        """N5: torch.cuda.OutOfMemoryError → status error + RU hint."""
        import torch
        engine = mock.MagicMock()
        engine.status.return_value = {"ready": True, "loaded": True, "weight": "sam3.pt"}
        with (
            mock.patch.object(prop, "get_sam3_engine", return_value=engine),
            mock.patch.object(prop, "_resolve_video", return_value=(self._video, "archive/clip.mp4")),
            mock.patch.object(prop, "resolve_named_weight", return_value=self._tmp / "sam3.pt"),
            mock.patch.object(prop, "_unload_yolo_seg"),
            mock.patch.object(
                prop, "_run_video_predictor",
                side_effect=torch.cuda.OutOfMemoryError("CUDA out of memory"),
            ),
        ):
            (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
            started = prop.start(
                video_path="archive/clip.mp4",
                time_sec=0.0,
                max_frames=5,
                bboxes=[{"x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.4}],
                persist=False,
            )
            st = self._wait(started["task_id"], timeout=8.0)
            self.assertEqual(st["status"], "error")
            self.assertIn("CUDA out of memory", st["message"])


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
