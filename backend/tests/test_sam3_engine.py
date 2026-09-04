"""P3.13.3a: SAM3 refine engine (mocked Ultralytics SAM)."""
from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from services import sam3_engine as sam
from services import segmentation_engine as seg


class _FakeMasks:
    def __init__(self, xyn=None, data=None) -> None:
        self.xyn = xyn
        self.data = data


class _FakeResult:
    def __init__(self, masks: _FakeMasks) -> None:
        self.masks = masks


class Sam3EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self._prev_sam = sam.MODELS_DIR
        self._prev_seg = seg.MODELS_DIR
        sam.MODELS_DIR = self._tmp
        seg.MODELS_DIR = self._tmp
        sam._engine = None
        self.engine = sam.Sam3Engine()
        self.seg_engine = seg.SegmentationEngine()

    def tearDown(self) -> None:
        sam.MODELS_DIR = self._prev_sam
        seg.MODELS_DIR = self._prev_seg
        sam._engine = None
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def _jpeg(self, size: int = 32) -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", (size, size), (10, 20, 30)).save(buf, "JPEG")
        return buf.getvalue()

    def test_status_not_ready_without_weight(self) -> None:
        st = self.engine.status()
        self.assertFalse(st["ready"])
        self.assertFalse(st["loaded"])
        self.assertEqual(st["available"], [])

    def test_whitelist_only_sam3(self) -> None:
        (self._tmp / "sam2.pt").write_bytes(b"\x00" * 2048)
        self.assertEqual(sam.list_available_weights(), [])
        with self.assertRaises(ValueError):
            sam.resolve_named_weight("sam2.pt")

    def test_mask_to_polygon_norm(self) -> None:
        mask = np.zeros((40, 40), dtype=np.uint8)
        mask[10:30, 10:30] = 255
        poly = sam.mask_to_polygon_norm(mask)
        self.assertGreaterEqual(len(poly), 3)
        for x, y in poly:
            self.assertGreaterEqual(x, 0.0)
            self.assertLessEqual(x, 1.0)
            self.assertGreaterEqual(y, 0.0)
            self.assertLessEqual(y, 1.0)

    def test_infer_prompts_with_points(self) -> None:
        (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
        fake_model = mock.MagicMock(
            return_value=[
                _FakeResult(
                    _FakeMasks(
                        xyn=[
                            np.array(
                                [[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]],
                                dtype=np.float64,
                            )
                        ]
                    )
                )
            ]
        )
        with mock.patch.object(sam, "_load_sam", return_value=fake_model):
            self.engine.load_model()
            out = self.engine.infer_prompts(
                self._jpeg(),
                points_norm=[{"x": 0.5, "y": 0.5, "label": 1}],
            )
        self.assertEqual(len(out["masks"]), 1)
        self.assertEqual(out["masks"][0]["class"], "object")
        self.assertGreaterEqual(len(out["masks"][0]["polygon_norm"]), 3)
        self.assertTrue(self.engine.status()["loaded"])

    def test_infer_requires_prompts(self) -> None:
        (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
        with mock.patch.object(sam, "_load_sam", return_value=mock.MagicMock()):
            self.engine.load_model()
        with self.assertRaises(ValueError):
            self.engine.infer_prompts(self._jpeg())

    def test_mutual_unload_sam_loads_clears_yolo(self) -> None:
        (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
        (self._tmp / "yolo26n-seg.pt").write_bytes(b"\x00" * 2048)
        with mock.patch.object(seg, "_load_yolo", return_value=mock.MagicMock()):
            self.seg_engine.load_model()
        self.assertTrue(self.seg_engine.status()["loaded"])

        with (
            mock.patch(
                "services.segmentation_engine.get_seg_engine",
                return_value=self.seg_engine,
            ),
            mock.patch.object(sam, "_load_sam", return_value=mock.MagicMock()),
        ):
            self.engine.load_model()

        self.assertTrue(self.engine.status()["loaded"])
        self.assertFalse(self.seg_engine.status()["loaded"])

    def test_mutual_unload_yolo_loads_clears_sam(self) -> None:
        (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
        (self._tmp / "yolo26n-seg.pt").write_bytes(b"\x00" * 2048)
        with mock.patch.object(sam, "_load_sam", return_value=mock.MagicMock()):
            self.engine.load_model()
        self.assertTrue(self.engine.status()["loaded"])

        with (
            mock.patch(
                "services.sam3_engine.get_sam3_engine",
                return_value=self.engine,
            ),
            mock.patch.object(seg, "_load_yolo", return_value=mock.MagicMock()),
        ):
            self.seg_engine.load_model()

        self.assertTrue(self.seg_engine.status()["loaded"])
        self.assertFalse(self.engine.status()["loaded"])

    def test_normalize_text_prompts(self) -> None:
        self.assertEqual(sam.normalize_text_prompts([" trench ", "person"]), ["trench", "person"])
        with self.assertRaises(ValueError):
            sam.normalize_text_prompts([])
        with self.assertRaises(ValueError):
            sam.normalize_text_prompts(["a", "b", "c", "d"])
        with self.assertRaises(ValueError):
            sam.normalize_text_prompts(["x" * 65])

    def test_infer_text(self) -> None:
        (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
        fake_pred = mock.MagicMock(
            return_value=[
                _FakeResult(
                    _FakeMasks(
                        xyn=[
                            np.array(
                                [[0.2, 0.2], [0.8, 0.2], [0.5, 0.8]],
                                dtype=np.float64,
                            )
                        ]
                    )
                )
            ]
        )
        with (
            mock.patch.object(sam, "_load_sam", return_value=mock.MagicMock()),
            mock.patch.object(sam, "_load_semantic_predictor", return_value=fake_pred),
        ):
            self.engine.load_model()
            out = self.engine.infer_text(self._jpeg(), ["trench", "person"])
        self.assertEqual(len(out["masks"]), 1)
        self.assertEqual(out["masks"][0]["class"], "trench")
        fake_pred.assert_called()
        kwargs = fake_pred.call_args.kwargs
        self.assertEqual(kwargs.get("text"), ["trench", "person"])

    def test_semantic_cache_cleared_on_unload(self) -> None:
        (self._tmp / "sam3.pt").write_bytes(b"\x00" * 2048)
        fake_pred = mock.MagicMock(return_value=[])
        with (
            mock.patch.object(sam, "_load_sam", return_value=mock.MagicMock()),
            mock.patch.object(sam, "_load_semantic_predictor", return_value=fake_pred) as load_sem,
        ):
            self.engine.load_model()
            self.engine.infer_text(self._jpeg(), ["person"])
            self.assertIsNotNone(self.engine._semantic_predictor)
            self.engine.unload_model()
            self.assertIsNone(self.engine._semantic_predictor)
            self.engine.load_model()
            self.engine.infer_text(self._jpeg(), ["vehicle"])
            self.assertEqual(load_sem.call_count, 2)


if __name__ == "__main__":
    unittest.main()
