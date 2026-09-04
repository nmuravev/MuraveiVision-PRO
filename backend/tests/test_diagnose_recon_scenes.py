"""Unit tests for recon diagnose (temp job dirs, no GPU)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from services.recon_diagnose import (
    diagnose_job,
    exit_code_for,
    get_best_sparse_dir,
    scan_recon_root,
)


class ReconDiagnoseTests(unittest.TestCase):
    def test_missing_job_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            diag = diagnose_job(root / "missing", cuda=False, gsplat=False)
            self.assertIn("job_dir_missing", diag.issues)
            self.assertFalse(diag.ok)

    def test_colmap_done_needs_train(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "abc123"
            sparse0 = job / "colmap" / "sparse" / "0"
            sparse0.mkdir(parents=True)
            (sparse0 / "points3D.txt").write_text(
                "# 3D point list\n1 0 0 0 255 0 0 0\n",
                encoding="utf-8",
            )
            frames = job / "frames"
            frames.mkdir()
            (frames / "000001.jpg").write_bytes(b"jpeg")
            (job / "camera_poses.json").write_text("[]", encoding="utf-8")
            (job / "sparse_points.json").write_text("[]", encoding="utf-8")
            (job / "manifest.json").write_text(
                json.dumps(
                    {
                        "job_id": "abc123",
                        "status": "colmap_done",
                        "artifact": None,
                        "video_path": "archive/test.mp4",
                    }
                ),
                encoding="utf-8",
            )

            diag = diagnose_job(job, cuda=True, gsplat=True)
            self.assertTrue(diag.colmap_sparse)
            self.assertEqual(diag.frames_count, 1)
            self.assertTrue(diag.needs_train)
            if diag.trainer_ready:
                self.assertIn("needs_gsplat_train", diag.issues)
            else:
                self.assertIn("trainer_missing", diag.issues)
            self.assertFalse(diag.ok)

            code = exit_code_for([diag], root)
            self.assertEqual(code, 2)

    def test_model_ply_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job = root / "done1"
            sparse0 = job / "colmap" / "sparse" / "0"
            sparse0.mkdir(parents=True)
            (sparse0 / "points3D.bin").write_bytes(b"bin")
            frames = job / "frames"
            frames.mkdir()
            (frames / "000001.jpg").write_bytes(b"jpeg")
            (job / "model.ply").write_text("ply\n", encoding="utf-8")
            (job / "manifest.json").write_text(
                json.dumps(
                    {
                        "job_id": "done1",
                        "status": "done",
                        "artifact": "model.ply",
                    }
                ),
                encoding="utf-8",
            )

            diag = diagnose_job(job, cuda=True, gsplat=True)
            self.assertTrue(diag.ok)
            self.assertFalse(diag.needs_train)
            self.assertEqual(exit_code_for([diag], root), 0)

    def test_scan_recon_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for jid in ("j1", "j2"):
                job = root / jid
                job.mkdir()
                (job / "manifest.json").write_text(
                    json.dumps({"job_id": jid, "status": "colmap_done"}),
                    encoding="utf-8",
                )
            all_jobs = scan_recon_root(root)
            self.assertEqual({d.job_id for d in all_jobs}, {"j1", "j2"})
            one = scan_recon_root(root, job_id="j1")
            self.assertEqual(len(one), 1)
            self.assertEqual(one[0].job_id, "j1")

    def test_best_sparse_prefers_larger_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "multi"
            sparse0 = job / "colmap" / "sparse" / "0"
            sparse1 = job / "colmap" / "sparse" / "1"
            sparse0.mkdir(parents=True)
            sparse1.mkdir(parents=True)
            # Tiny/broken model in 0
            (sparse0 / "points3D.txt").write_text("# tiny\n", encoding="utf-8")
            (sparse0 / "cameras.txt").write_text("# cam\n", encoding="utf-8")
            # Larger valid model in 1
            big_pts = "# 3D point list\n" + "\n".join(
                f"{i} {i}.0 0.0 0.0 255 0 0 0" for i in range(1, 40)
            )
            (sparse1 / "points3D.txt").write_text(big_pts, encoding="utf-8")
            (sparse1 / "cameras.txt").write_text("# cam\n", encoding="utf-8")

            best = get_best_sparse_dir(job)
            self.assertIsNotNone(best)
            assert best is not None
            self.assertEqual(best.name, "1")

            frames = job / "frames"
            frames.mkdir()
            (frames / "000001.jpg").write_bytes(b"jpeg")
            (job / "manifest.json").write_text(
                json.dumps(
                    {
                        "job_id": "multi",
                        "status": "colmap_done",
                        "artifact": None,
                    }
                ),
                encoding="utf-8",
            )
            diag = diagnose_job(job, cuda=True, gsplat=True)
            self.assertTrue(diag.colmap_sparse)
            self.assertNotIn("missing_colmap_sparse", diag.issues)
            self.assertTrue(diag.needs_train)


if __name__ == "__main__":
    unittest.main()
