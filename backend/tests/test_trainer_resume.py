"""P1.8: resume checkpoints, detect-only guard, missing last.pt."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import trainer


class TrainerResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self.weights = self._tmp / "weights"
        self.weights.mkdir(parents=True)

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def _pt(self, name: str, size: int = 2048) -> Path:
        p = self.weights / name
        p.write_bytes(b"\x00" * size)
        return p

    def test_list_checkpoints_skips_seg(self) -> None:
        self._pt("last.pt")
        self._pt("best.pt")
        self._pt("epoch10.pt")
        self._pt("yoloe-26n-seg.pt")
        self._pt("yolo26n.pt")
        csv = self.weights.parent / "results.csv"
        csv.write_text(
            "epoch,metrics/mAP50(B)\n9,0.42\n",
            encoding="utf-8",
        )
        with mock.patch.object(trainer, "_ckpt_dirs", return_value=[self.weights]):
            out = trainer.list_checkpoints()
        names = {c["name"] for c in out["checkpoints"]}
        self.assertIn("last.pt", names)
        self.assertIn("best.pt", names)
        self.assertIn("epoch10.pt", names)
        self.assertNotIn("yoloe-26n-seg.pt", names)
        self.assertNotIn("yolo26n.pt", names)
        self.assertTrue(out["can_resume"])
        self.assertEqual(out["resume_from"], "last.pt")
        last = next(c for c in out["checkpoints"] if c["name"] == "last.pt")
        self.assertTrue(last["resumable"])
        self.assertEqual(last["metrics"]["map50"], 0.42)

    def test_resolve_resume_missing(self) -> None:
        with mock.patch.object(trainer, "_ckpt_dirs", return_value=[self.weights]):
            with self.assertRaises(FileNotFoundError):
                trainer.resolve_resume("last.pt")

    def test_resolve_resume_rejects_seg_name(self) -> None:
        with self.assertRaises(ValueError):
            trainer.resolve_resume("yoloe-26s-seg.pt")
        with self.assertRaises(ValueError):
            trainer.resolve_resume("../last.pt/../../secret.pt")

    def test_resolve_resume_ok(self) -> None:
        self._pt("last.pt")
        with mock.patch.object(trainer, "_ckpt_dirs", return_value=[self.weights]):
            path = trainer.resolve_resume("last.pt")
        self.assertEqual(path.name, "last.pt")

    def test_is_detect_base_rejects_seg(self) -> None:
        seg = self._pt("yolo26n-seg.pt")
        self.assertFalse(trainer._is_detect_base(seg))
        ok = self._pt("last.pt")
        self.assertTrue(trainer._is_detect_base(ok))

    def test_start_missing_checkpoint_does_not_run(self) -> None:
        with mock.patch.object(trainer, "_ckpt_dirs", return_value=[self.weights]):
            with self.assertRaises(FileNotFoundError):
                trainer.start(resume_from="last.pt")
        self.assertNotEqual(trainer.status().get("status"), "running")

    def test_batch_retry_sequence(self) -> None:
        self.assertEqual(trainer._train_batches("cuda", 4), (4, 2, 1))
        self.assertEqual(trainer.clamp_imgsz(640), 640)
        self.assertEqual(trainer.clamp_imgsz(1000), 992)
        self.assertEqual(trainer.clamp_batch(99), 8)


if __name__ == "__main__":
    unittest.main()
