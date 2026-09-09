"""Unit tests: YOLO DirectML provider selection + ONNX cache + fallback."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.yolo_directml import (
    ensure_onnx_export,
    onnx_cache_path,
    select_inference_backend,
)


class YoloDirectmlTests(unittest.TestCase):
    def test_select_auto_prefers_cuda(self) -> None:
        self.assertEqual(
            select_inference_backend("auto", torch_cuda=True, dml_ok=True),
            "torch-cuda",
        )

    def test_select_auto_dml_when_no_cuda(self) -> None:
        self.assertEqual(
            select_inference_backend("auto", torch_cuda=False, dml_ok=True),
            "directml",
        )

    def test_select_auto_cpu(self) -> None:
        self.assertEqual(
            select_inference_backend("auto", torch_cuda=False, dml_ok=False),
            "cpu",
        )

    def test_select_directml_falls_back_without_provider(self) -> None:
        self.assertEqual(
            select_inference_backend("directml", torch_cuda=False, dml_ok=False),
            "cpu",
        )

    def test_select_torch_explicit(self) -> None:
        self.assertEqual(
            select_inference_backend("torch", torch_cuda=False, dml_ok=True),
            "cpu",
        )
        self.assertEqual(
            select_inference_backend("torch", torch_cuda=True, dml_ok=True),
            "torch-cuda",
        )

    def test_onnx_cache_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            weights = Path(td) / "toy.pt"
            weights.write_bytes(b"fake-pt-bytes-xxxx")
            onnx = onnx_cache_path(weights)
            onnx.parent.mkdir(parents=True, exist_ok=True)
            onnx.write_bytes(b"x" * 2048)
            # Newer onnx than pt → no export call
            with mock.patch("ultralytics.YOLO") as yolo_cls:
                path = ensure_onnx_export(weights, imgsz=640)
                self.assertEqual(path, onnx)
                yolo_cls.assert_not_called()

    def test_onnx_export_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            weights = Path(td) / "toy.pt"
            weights.write_bytes(b"fake-pt-bytes-xxxx")
            out = onnx_cache_path(weights)

            class _FakeModel:
                def export(self, **_kwargs):
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(b"y" * 2048)
                    return str(out)

            with mock.patch("ultralytics.YOLO", return_value=_FakeModel()):
                path = ensure_onnx_export(weights, imgsz=640)
                self.assertTrue(path.is_file())
                self.assertGreater(path.stat().st_size, 1024)
                self.assertIn("onnx_cache", str(path).replace("\\", "/"))



    def test_onnx_export_never_leaves_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            weights = Path(td) / "toy.pt"
            weights.write_bytes(b"fake-pt-bytes-xxxx")
            sibling = weights.with_suffix(".onnx")
            out = onnx_cache_path(weights)

            class _FakeModel:
                def export(self, **_kwargs):
                    # Simulate bad export beside weights
                    sibling.write_bytes(b"z" * 2048)
                    return str(sibling)

            with mock.patch("ultralytics.YOLO", return_value=_FakeModel()):
                path = ensure_onnx_export(weights, imgsz=640)
            self.assertTrue(path.is_file())
            self.assertIn("onnx_cache", str(path).replace("\\", "/"))
            self.assertFalse(sibling.is_file(), "sibling ONNX beside .pt must be removed")


if __name__ == "__main__":
    unittest.main()
