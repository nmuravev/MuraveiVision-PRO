"""P3.13 v1: archive-only YOLO26-seg, detect ≠ segment."""
from __future__ import annotations

import inspect
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from services import segmentation_engine as seg


class _FakeMasks:
    def __init__(self, xyn: list[np.ndarray]) -> None:
        self.xyn = xyn


class _FakeBoxes:
    def __init__(self, cls: list[int], conf: list[float]) -> None:
        self.cls = np.array(cls, dtype=np.float32)
        self.conf = np.array(conf, dtype=np.float32)


class _FakeResult:
    def __init__(self) -> None:
        self.names = {0: "trench", 1: "person"}
        self.masks = _FakeMasks(
            [
                np.array([[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]], dtype=np.float64),
                np.array([[0.2, 0.2], [0.3, 0.2], [0.3, 0.4], [0.2, 0.4]], dtype=np.float64),
            ]
        )
        self.boxes = _FakeBoxes([0, 1], [0.91, 0.44])


class SegmentationEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self._prev_dir = seg.MODELS_DIR
        seg.MODELS_DIR = self._tmp
        self.engine = seg.SegmentationEngine()

    def tearDown(self) -> None:
        seg.MODELS_DIR = self._prev_dir
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def _jpeg(self) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", (32, 32), (20, 40, 60)).save(buf, "JPEG")
        return buf.getvalue()

    def test_status_not_ready_without_weight(self) -> None:
        st = self.engine.status()
        self.assertFalse(st["ready"])
        self.assertFalse(st["loaded"])
        self.assertIsNone(st["weight"])
        self.assertEqual(st["available"], [])
        self.assertEqual(st["imgsz"], 640)

    def test_ignores_yoloe_seg_weight(self) -> None:
        (self._tmp / "yoloe-26n-seg.pt").write_bytes(b"\x00" * 2048)
        self.assertIsNone(seg.resolve_seg_weights())
        self.assertFalse(self.engine.status()["ready"])

    def test_prefers_nano_over_small(self) -> None:
        (self._tmp / "yolo26s-seg.pt").write_bytes(b"\x00" * 2048)
        (self._tmp / "yolo26n-seg.pt").write_bytes(b"\x00" * 2048)
        path = seg.resolve_seg_weights()
        self.assertIsNotNone(path)
        assert path is not None
        self.assertEqual(path.name, "yolo26n-seg.pt")
        self.assertTrue(self.engine.status()["ready"])

    def test_infer_without_weight_raises(self) -> None:
        with self.assertRaises(RuntimeError):
            self.engine.infer_jpeg(self._jpeg(), 0.3)

    def test_infer_mock_predict_polygons(self) -> None:
        (self._tmp / "yolo26n-seg.pt").write_bytes(b"\x00" * 2048)
        fake = mock.Mock()
        fake.predict.return_value = [_FakeResult()]
        with mock.patch.object(seg, "_load_yolo", return_value=fake):
            self.engine.load_model("yolo26n-seg.pt")
            out = self.engine.infer_jpeg(self._jpeg(), 0.3)
        self.assertEqual(len(out["masks"]), 2)
        first = out["masks"][0]
        self.assertEqual(first["class"], "trench")
        self.assertAlmostEqual(first["conf"], 0.91, places=4)
        self.assertGreaterEqual(len(first["polygon_norm"]), 3)
        for x, y in first["polygon_norm"]:
            self.assertGreaterEqual(x, 0.0)
            self.assertLessEqual(x, 1.0)
            self.assertGreaterEqual(y, 0.0)
            self.assertLessEqual(y, 1.0)
        self.assertEqual(out["masks"][1]["class"], "person")
        fake.predict.assert_called_once()
        kwargs = fake.predict.call_args.kwargs
        self.assertEqual(kwargs["imgsz"], 640)
        self.assertEqual(kwargs["conf"], 0.3)
        self.assertIsNotNone(self.engine._model)

    def test_load_model_missing(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.engine.load_model("yolo26n-seg.pt")
        self.assertFalse(self.engine.status()["loaded"])

    def test_load_rejects_yoloe_seg(self) -> None:
        (self._tmp / "yoloe-26n-seg.pt").write_bytes(b"\x00" * 2048)
        with self.assertRaises(ValueError):
            self.engine.load_model("yoloe-26n-seg.pt")
        with self.assertRaises(ValueError):
            self.engine.load_model("../secret.pt")
        with self.assertRaises(ValueError):
            self.engine.load_model("yolo26n.pt")
        self.assertFalse(self.engine.status()["loaded"])

    def test_unload_clears(self) -> None:
        (self._tmp / "yolo26n-seg.pt").write_bytes(b"\x00" * 2048)
        fake = mock.Mock()
        with mock.patch.object(seg, "_load_yolo", return_value=fake):
            self.engine.load_model("yolo26n-seg.pt")
        self.assertTrue(self.engine.status()["loaded"])
        self.engine.unload_model()
        self.assertFalse(self.engine.status()["loaded"])
        self.assertIsNone(self.engine._model)

    def test_infer_without_load_raises(self) -> None:
        (self._tmp / "yolo26n-seg.pt").write_bytes(b"\x00" * 2048)
        self.assertTrue(self.engine.status()["ready"])
        self.assertFalse(self.engine.status()["loaded"])
        with self.assertRaises(RuntimeError):
            self.engine.infer_jpeg(self._jpeg(), 0.3)

    def test_module_does_not_touch_detect_train(self) -> None:
        src = inspect.getsource(seg)
        self.assertNotIn("from services.yolo_engine", src)
        self.assertNotIn("from services.trainer", src)
        self.assertNotIn("insert_detection", src)
        api_src = inspect.getsource(__import__("api.seg", fromlist=["seg"]))
        self.assertNotIn("insert_detection", api_src)
        self.assertNotIn("from services.yolo_engine", api_src)
        self.assertNotIn("from services.trainer", api_src)
