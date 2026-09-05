"""Tests for AliceVision dense pipeline helpers (no GPU required)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import alicevision_pipeline as avp


class TestNormalizeArtifacts(unittest.TestCase):
    def test_infers_sparse_and_splat(self) -> None:
        man = {
            "sparse_file": "sparse_points.json",
            "artifact": "model.ply",
        }
        out = avp.normalize_artifacts(man)
        self.assertEqual(out["artifacts"]["sparse"]["file"], "sparse_points.json")
        self.assertEqual(out["artifacts"]["splat"]["file"], "model.ply")
        self.assertIn(out["selected_artifact"], ("splat", "sparse"))

    def test_prefers_mesh_selection(self) -> None:
        man = {
            "artifacts": {
                "sparse": {"file": "sparse_points.json"},
                "dense": {"file": "dense_point_cloud.ply"},
                "mesh": {"file": "textured_mesh.obj"},
            }
        }
        out = avp.normalize_artifacts(man)
        self.assertEqual(out["selected_artifact"], "mesh")

    def test_legacy_dense_ply_artifact(self) -> None:
        man = {"artifact": "dense_point_cloud.ply", "sparse_file": "sparse_points.json"}
        out = avp.normalize_artifacts(man)
        self.assertEqual(out["artifacts"]["dense"]["file"], "dense_point_cloud.ply")


class TestPipelineFallback(unittest.TestCase):
    def test_missing_alicevision_graceful(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            (job / "frames").mkdir()
            with patch.object(avp, "alicevision_available", return_value=False):
                result = avp.run_dense_pipeline(job, mode="dense")
        self.assertFalse(result["ok"])
        self.assertIn("AliceVision", result["error"] or "")
        self.assertEqual(result["artifacts"], {})

    def test_no_cuda_graceful(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            (job / "frames").mkdir()
            with patch.object(avp, "alicevision_available", return_value=True):
                with patch.object(
                    avp,
                    "alicevision_cuda_ready",
                    return_value=(False, "нет CUDA"),
                ):
                    result = avp.run_dense_pipeline(job, mode="mesh")
        self.assertFalse(result["ok"])
        self.assertIn("CUDA", result["error"] or result["warning"] or "")

    def test_patch_manifest_keeps_sparse_on_fail(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            (job / "sparse_points.json").write_text("{}", encoding="utf-8")
            man = {"status": "colmap_done", "sparse_file": "sparse_points.json"}
            out = avp.patch_manifest_artifacts(
                man,
                job,
                {"ok": False, "artifacts": {}, "warning": "boom", "error": "boom"},
            )
        self.assertEqual(out["status"], "colmap_done")
        self.assertEqual(out["alicevision_warning"], "boom")
        self.assertEqual(out["artifacts"]["sparse"]["file"], "sparse_points.json")

    def test_ensure_colmap_text_converts_bin(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sparse = Path(td) / "sparse"
            sparse.mkdir()
            (sparse / "cameras.bin").write_bytes(b"bin")
            (sparse / "images.bin").write_bytes(b"bin")

            def _fake_convert(*_a, **_k):
                (sparse / "cameras.txt").write_text("1 PINHOLE 10 10 5 5 5 5\n", encoding="utf-8")
                (sparse / "images.txt").write_text(
                    "1 0 0 0 1 0 0 0 1 1.jpg\n",
                    encoding="utf-8",
                )

            with patch("services.recon_scanner._colmap_bin", return_value="colmap"):
                with patch("services.runtime_log.logged_run", side_effect=_fake_convert):
                    ok = avp.ensure_colmap_text_model(sparse)
            self.assertTrue(ok)
            self.assertTrue((sparse / "cameras.txt").is_file())

    def test_ensure_colmap_text_already_present(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sparse = Path(td)
            (sparse / "cameras.txt").write_text("x", encoding="utf-8")
            (sparse / "images.txt").write_text("y", encoding="utf-8")
            self.assertTrue(avp.ensure_colmap_text_model(sparse))


class TestInjectColmapPoses(unittest.TestCase):
    def test_inject_matches_by_basename(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            frames = root / "frames"
            frames.mkdir()
            (frames / "000001.jpg").write_bytes(b"x")
            (frames / "000002.jpg").write_bytes(b"x")
            sparse = root / "sparse"
            sparse.mkdir()
            (sparse / "cameras.txt").write_text(
                "#\n1 PINHOLE 100 80 50 50 50 40\n",
                encoding="utf-8",
            )
            (sparse / "images.txt").write_text(
                "#\n"
                "1 1 0 0 0 0 0 0 1 000001.jpg\n\n"
                "2 1 0 0 0 0.1 0 0 1 000002.jpg\n\n",
                encoding="utf-8",
            )
            cam_init = {
                "version": ["1", "2", "12"],
                "views": [
                    {
                        "viewId": "10",
                        "poseId": "10",
                        "frameId": "1",
                        "intrinsicId": "99",
                        "path": str(frames / "000001.jpg"),
                        "width": "100",
                        "height": "80",
                    },
                    {
                        "viewId": "20",
                        "poseId": "20",
                        "frameId": "2",
                        "intrinsicId": "99",
                        "path": str(frames / "000002.jpg"),
                        "width": "100",
                        "height": "80",
                    },
                ],
                "intrinsics": [],
                "poses": [],
            }
            init_path = root / "cameraInit.sfm"
            init_path.write_text(json.dumps(cam_init), encoding="utf-8")
            out = root / "out.sfm"
            n = avp.inject_colmap_poses(init_path, sparse, frames, out)
            self.assertEqual(n, 2)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(len(data["poses"]), 2)
            self.assertEqual(len(data["views"]), 2)
            self.assertTrue(data["intrinsics"])


if __name__ == "__main__":
    unittest.main()
