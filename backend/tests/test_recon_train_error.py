"""Train error snippet + MSVC preflight helpers."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from services.gsplat_msvc import MSVC_NEED_MSG, clear_caches, gsplat_train_ready
from services import recon_train
from services.recon_train import format_train_error
from services import train_presets


class TestFormatTrainError(unittest.TestCase):
    def test_empty_lines(self) -> None:
        self.assertEqual(format_train_error(1, []), "exit code 1")

    def test_prefers_important(self) -> None:
        lines = [
            "loading data…",
            "step 1 loss=0.5",
            "RuntimeError: cannot find cl.exe",
            "gsplat_train: CUDA JIT failed",
        ]
        err = format_train_error(1, lines)
        self.assertTrue(err.startswith("exit code 1:"))
        self.assertIn("cl.exe", err)
        self.assertIn("gsplat_train:", err)

    def test_falls_back_to_tail(self) -> None:
        lines = ["alpha", "beta", "gamma"]
        err = format_train_error(2, lines)
        self.assertEqual(err, "exit code 2: alpha | beta | gamma")

    def test_control_c_exit_unsigned(self) -> None:
        err = format_train_error(3221225786, ["Traceback (most recent call last):"])
        self.assertIn("прервано", err)
        self.assertNotIn("Traceback", err)

    def test_control_c_exit_signed(self) -> None:
        err = format_train_error(-1073741510, [])
        self.assertIn("прервано", err)


class TestGsplatMsvcReady(unittest.TestCase):
    def tearDown(self) -> None:
        clear_caches()

    def test_ready_when_cl_on_path(self) -> None:
        with patch("services.gsplat_msvc.cl_on_path", return_value=True):
            ok, reason = gsplat_train_ready()
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_not_ready_without_cl_or_vcvars(self) -> None:
        with (
            patch("services.gsplat_msvc.cl_on_path", return_value=False),
            patch("services.gsplat_msvc.find_vcvars64", return_value=None),
            patch("services.gsplat_msvc.os.name", "nt"),
        ):
            ok, reason = gsplat_train_ready()
        self.assertFalse(ok)
        self.assertEqual(reason, MSVC_NEED_MSG)


class TestPresetsMsvcGate(unittest.TestCase):
    def test_gsplat_disabled_without_msvc(self) -> None:
        with (
            patch.object(train_presets, "total_vram_gb", return_value=16.0),
            patch("services.gsplat_msvc.gsplat_train_ready", return_value=(False, MSVC_NEED_MSG)),
        ):
            items = train_presets.presets_for_client()
        bal = next(i for i in items if i["id"] == "balanced")
        boot = next(i for i in items if i["id"] == "bootstrap")
        self.assertTrue(bal["disabled"])
        self.assertIn("MSVC", bal["disabled_reason"])
        self.assertFalse(boot["disabled"])


class TestParseTqdmProgress(unittest.TestCase):
    def setUp(self) -> None:
        with recon_train._lock:
            recon_train._state.update(
                {
                    "status": "training",
                    "job_id": "deadbeefcafe",
                    "preset": "balanced",
                    "steps": 0,
                    "max_steps": 7000,
                    "loss": None,
                    "psnr": None,
                    "message": "",
                    "error": None,
                    "artifact": None,
                }
            )
            recon_train._events.clear()
            recon_train._thread = None
            recon_train._proc = None

    def test_tqdm_train_bar_updates_steps(self) -> None:
        line = "loss=0.053| sh degree=2| :  30%|███       | 2123/7000 [00:21<00:45, 106.41it/s]"
        recon_train._parse_line(line, 7000)
        self.assertEqual(recon_train._state["steps"], 2123)
        self.assertEqual(recon_train._state["max_steps"], 7000)
        self.assertAlmostEqual(float(recon_train._state["loss"]), 0.053)

    def test_downscale_bar_ignored(self) -> None:
        recon_train._parse_line("100%|██████████| 121/121 [00:01<00:00, 67.59it/s]", 7000)
        self.assertEqual(recon_train._state["steps"], 0)

    def test_stale_training_recovered(self) -> None:
        st = recon_train.status()
        self.assertEqual(st["status"], "error")
        self.assertIn("прервано", st["error"] or "")


class TestPatchArtifactClearsNextAction(unittest.TestCase):
    def test_model_ply_drops_balanced_cta(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            (job / "model.ply").write_bytes(b"ply\n")
            (job / "manifest.json").write_text(
                json.dumps(
                    {
                        "job_id": "deadbeefcafe",
                        "status": "colmap_done",
                        "artifact": None,
                        "next_action": "balanced_for_splat",
                    }
                ),
                encoding="utf-8",
            )
            art = recon_train._patch_artifact(job)
            self.assertEqual(art, "model.ply")
            man = json.loads((job / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(man["status"], "done")
            self.assertEqual(man["artifact"], "model.ply")
            self.assertNotIn("next_action", man)


if __name__ == "__main__":
    unittest.main()
