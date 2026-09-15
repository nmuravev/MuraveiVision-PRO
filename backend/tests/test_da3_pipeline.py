"""Unit and integration tests for Depth Anything 3 (DA3) Dense backend."""
from __future__ import annotations

import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import numpy as np
except ImportError:
    import types
    class MockArray:
        def __init__(self, data, shape=None):
            self.data = data
            self.shape = shape or (len(data), len(data[0])) if isinstance(data, list) and data and isinstance(data[0], list) else (len(data),) if isinstance(data, list) else ()
            self.T = self
        def __len__(self):
            return self.shape[0] if self.shape else 0
        def __getitem__(self, item):
            if isinstance(item, tuple) and len(item) == 2:
                r, c = item
                if isinstance(self.data, list) and isinstance(r, int) and isinstance(c, int):
                    return self.data[r][c]
            return 1.0
        def __mul__(self, other):
            return self
        def __rmul__(self, other):
            return self
        def __sub__(self, other):
            return self
        def __gt__(self, other):
            return self
        def __lt__(self, other):
            return self
        def __and__(self, other):
            return self
        def __invert__(self):
            return self
        def astype(self, dt):
            return self

    class MockNumpy(types.ModuleType):
        float32 = "float32"
        uint8 = "uint8"
        float64 = "float64"
        nan = float("nan")

        @staticmethod
        def array(data, dtype=None):
            return MockArray(data)
        @staticmethod
        def zeros(shape, dtype=None):
            return MockArray(0.0, shape=shape)
        @staticmethod
        def empty(shape, dtype=None):
            return MockArray([], shape=shape)
        @staticmethod
        def ones(shape, dtype=None):
            return MockArray(1.0, shape=shape)
        @staticmethod
        def concatenate(seq, axis=0):
            flat = []
            for item in seq:
                if hasattr(item, "data") and isinstance(item.data, list):
                    flat.extend(item.data)
                elif hasattr(item, "__iter__"):
                    flat.extend(list(item))
            return MockArray(flat)
        @staticmethod
        def eye(n, dtype=None):
            return MockArray([[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)])
        @staticmethod
        def mgrid():
            pass
        @staticmethod
        def median(arr):
            return 10.0
        @staticmethod
        def isfinite(arr):
            return True
        @staticmethod
        def isnan(arr):
            return False
        @staticmethod
        def any(arr):
            return True
        @staticmethod
        def clip(arr, a_min, a_max):
            return arr
        @staticmethod
        def ascontiguousarray(arr):
            return arr

    import sys
    np = MockNumpy("numpy")
    sys.modules["numpy"] = np

from services import da3_pipeline
from services.da3_pipeline import (
    DA3WeightsNotFoundError,
    find_da3_weights,
    get_da3_sidecar_dir,
    run_da3_pipeline,
    write_binary_ply,
)


class TestDA3WeightsDetection(unittest.TestCase):
    def test_missing_weights_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            with patch.object(da3_pipeline, "get_da3_sidecar_dir", return_value=Path(td)):
                self.assertIsNone(find_da3_weights("base"))
                self.assertIsNone(find_da3_weights("large"))

    def test_finds_safetensors_and_pt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sidecar = Path(td)
            (sidecar / "da3_base.safetensors").touch()
            (sidecar / "da3_large.pt").touch()
            with patch.object(da3_pipeline, "get_da3_sidecar_dir", return_value=sidecar):
                w_base = find_da3_weights("base")
                w_large = find_da3_weights("large")
                self.assertIsNotNone(w_base)
                self.assertIsNotNone(w_large)
                self.assertTrue(str(w_base).endswith("da3_base.safetensors"))
                self.assertTrue(str(w_large).endswith("da3_large.pt"))


class TestDA3PLYWriter(unittest.TestCase):
    def test_write_binary_ply_header_and_data(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "test_dense.ply"
            pts = [
                [1.0, 2.0, 3.0],
                [4.0, 5.0, 6.0],
            ]
            cols = [
                [255, 0, 0],
                [0, 255, 128],
            ]

            # Mock objects with shape (2, 3) and indexable
            class PtsMock:
                def __len__(self):
                    return 2
                def __getitem__(self, item):
                    r, c = item
                    return pts[r][c]

            class ColsMock:
                def __len__(self):
                    return 2
                def __getitem__(self, item):
                    r, c = item
                    return cols[r][c]

            write_binary_ply(out_path, PtsMock(), ColsMock())
            self.assertTrue(out_path.is_file())

            with out_path.open("rb") as f:
                header = b""
                while True:
                    line = f.readline()
                    header += line
                    if line.strip() == b"end_header":
                        break
                header_str = header.decode("ascii")
                self.assertIn("format binary_little_endian 1.0", header_str)
                self.assertIn("element vertex 2", header_str)
                self.assertIn("property float x", header_str)
                self.assertIn("property float y", header_str)
                self.assertIn("property float z", header_str)
                self.assertIn("property uchar red", header_str)
                self.assertIn("property uchar green", header_str)
                self.assertIn("property uchar blue", header_str)
                # Decision Q3: No normals in dense.ply
                self.assertNotIn("nx", header_str)

                payload = f.read()
                # 2 vertices * (12 bytes float + 3 bytes color) = 30 bytes
                self.assertEqual(len(payload), 30)

                x, y, z, r, g, b = struct.unpack("<fffBBB", payload[:15])
                self.assertAlmostEqual(x, 1.0, places=4)
                self.assertAlmostEqual(y, 2.0, places=4)
                self.assertAlmostEqual(z, 3.0, places=4)
                self.assertEqual((r, g, b), (255, 0, 0))


class TestDA3PipelineExecution(unittest.TestCase):
    def test_missing_weights_raises_exception(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            (job_dir / "camera_poses.json").write_text("{}", encoding="utf-8")
            with patch.object(da3_pipeline, "get_da3_sidecar_dir", return_value=Path(td) / "empty"):
                with self.assertRaises(DA3WeightsNotFoundError):
                    run_da3_pipeline(job_dir, variant="base")

    def test_soft_fail_few_cameras_preserves_colmap(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            sidecar = job_dir / "sidecars" / "da3"
            sidecar.mkdir(parents=True)
            (sidecar / "da3_base.safetensors").touch()

            poses = {
                "frames": [
                    {"frame": "frame_0001.jpg", "R": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "t": [0, 0, 0]},
                    {"frame": "frame_0002.jpg", "R": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "t": [0, 0, 0]},
                ]
            }
            (job_dir / "camera_poses.json").write_text(json.dumps(poses), encoding="utf-8")
            (job_dir / "manifest.json").write_text(json.dumps({"status": "colmap_done"}), encoding="utf-8")

            with patch.object(da3_pipeline, "get_da3_sidecar_dir", return_value=sidecar):
                res = run_da3_pipeline(job_dir, variant="base")
                self.assertFalse(res["ok"])
                self.assertIn("Недостаточно", res["error"])

                man = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(man["status"], "colmap_done")

    def test_mock_weights_end_to_end_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            sidecar = job_dir / "sidecars" / "da3"
            sidecar.mkdir(parents=True)
            (sidecar / "da3_base.safetensors").touch()

            frames_dir = job_dir / "frames"
            frames_dir.mkdir()
            frame_names = [f"frame_{i:04d}.jpg" for i in range(1, 10)]
            for fname in frame_names:
                (frames_dir / fname).write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)

            poses = {
                "frames": [
                    {
                        "frame": fname,
                        "R": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                        "t": [0, 0, 0],
                        "intrinsics": [50.0, 50.0, 32.0, 32.0],
                    }
                    for fname in frame_names
                ]
            }
            (job_dir / "camera_poses.json").write_text(json.dumps(poses), encoding="utf-8")
            (job_dir / "manifest.json").write_text(json.dumps({"status": "colmap_done"}), encoding="utf-8")

            events = []
            def collect_events(ev: dict) -> None:
                events.append(ev)

            # Mock loading images and unprojecting points
            mock_points = [[float(i), float(i), float(i)] for i in range(50)]
            mock_colors = [[200, 100, 50] for _ in range(50)]

            class PointsMock:
                def __len__(self):
                    return len(mock_points)
                def __getitem__(self, item):
                    r, c = item
                    return mock_points[r][c]

            class ColorsMock:
                def __len__(self):
                    return len(mock_colors)
                def __getitem__(self, item):
                    r, c = item
                    return mock_colors[r][c]

            with patch.object(da3_pipeline, "get_da3_sidecar_dir", return_value=sidecar):
                with patch.object(da3_pipeline, "_load_image_rgb", return_value=MagicMock(shape=(64, 64, 3))):
                    with patch.object(da3_pipeline, "_predict_depth_map", return_value=MagicMock(shape=(64, 64))):
                        with patch.object(da3_pipeline, "_unproject_pixels", return_value=(PointsMock(), ColorsMock())):
                            # mock_model required: empty .safetensors is not a usable runtime model
                            res = run_da3_pipeline(
                                job_dir,
                                variant="base",
                                mock_model=MagicMock(),
                                emit=collect_events,
                            )

            self.assertTrue(res["ok"])
            dense_ply = job_dir / "dense.ply"
            self.assertTrue(dense_ply.is_file())
            self.assertGreater(dense_ply.stat().st_size, 50)

            # Verify manifest updated
            man = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(man["artifacts"]["dense"], "dense.ply")
            self.assertEqual(man["artifact"], "dense.ply")

            # Intermediate depths directory should be cleaned up (Decision Q4)
            self.assertFalse((job_dir / "da3" / "depths").exists())

            # Verify streaming events (stages da3_depth, da3_fusion, da3_done)
            stages = [e.get("stage") for e in events if "stage" in e]
            self.assertIn("da3_depth", stages)
            self.assertIn("da3_fusion", stages)
            self.assertIn("da3_done", stages)

    def test_runtime_unavailable_no_flat_depth_no_dense_ply(self) -> None:
        """_load_da3_model → None must raise DA3_RUNTIME_UNAVAILABLE; no dense.ply."""
        from services.da3_pipeline import DA3WeightsNotFoundError, run_da3_pipeline
        from services import da3_pipeline

        with tempfile.TemporaryDirectory() as td:
            job_dir = Path(td)
            sidecar = job_dir / "sidecars" / "da3"
            sidecar.mkdir(parents=True)
            (sidecar / "da3_base.safetensors").write_bytes(b"fake")

            frames_dir = job_dir / "frames"
            frames_dir.mkdir()
            frame_names = [f"frame_{i:04d}.jpg" for i in range(1, 10)]
            for fname in frame_names:
                (frames_dir / fname).write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)

            poses = {
                "frames": [
                    {
                        "frame": fname,
                        "R": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                        "t": [0, 0, 0],
                        "intrinsics": [50.0, 50.0, 32.0, 32.0],
                    }
                    for fname in frame_names
                ]
            }
            (job_dir / "camera_poses.json").write_text(json.dumps(poses), encoding="utf-8")
            (job_dir / "manifest.json").write_text(json.dumps({"status": "colmap_done"}), encoding="utf-8")

            with patch.object(da3_pipeline, "get_da3_sidecar_dir", return_value=sidecar):
                with patch.object(da3_pipeline, "_load_da3_model", return_value=None):
                    with self.assertRaises(DA3WeightsNotFoundError) as ctx:
                        run_da3_pipeline(job_dir, variant="base")

            msg = str(ctx.exception)
            self.assertIn("DA3_RUNTIME_UNAVAILABLE", msg)
            self.assertFalse((job_dir / "dense.ply").exists())


if __name__ == "__main__":
    unittest.main()
