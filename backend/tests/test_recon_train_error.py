"""Train error snippet + MSVC preflight helpers."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from services.gsplat_msvc import MSVC_NEED_MSG, clear_caches, gsplat_train_ready
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


if __name__ == "__main__":
    unittest.main()
