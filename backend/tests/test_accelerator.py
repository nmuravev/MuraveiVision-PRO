"""Unit tests: accelerator_kind + CPU profile budgets."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from services import accelerator, recon_colmap
from services.accelerator import (
    CPU_BANNER_RU,
    CPU_COLMAP_MAX_FRAMES,
    CPU_COLMAP_MAX_IMAGE_SIZE,
    GSPLAT_CUDA_REASON_RU,
    clear_profile_log_flag,
)


class AcceleratorProfileTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("MURAVEI_FORCE_ACCELERATOR", None)
        os.environ.pop("MURAVEI_CPU_DISABLE_DENSE", None)
        os.environ.pop("COLMAP_MAX_IMAGE_SIZE", None)
        os.environ.pop("COLMAP_MAX_FRAMES", None)
        os.environ.pop("COLMAP_USE_GPU", None)
        clear_profile_log_flag()

    def test_force_cpu_kind(self) -> None:
        with mock.patch.dict(os.environ, {"MURAVEI_FORCE_ACCELERATOR": "cpu"}):
            self.assertEqual(accelerator.accelerator_kind(), "cpu")
            self.assertTrue(accelerator.is_cpu_profile())
            snap = accelerator.profile_snapshot()
            self.assertEqual(snap["banner"], CPU_BANNER_RU)
            self.assertFalse(snap["colmap_use_gpu"])

    def test_force_cuda_kind(self) -> None:
        with mock.patch.dict(os.environ, {"MURAVEI_FORCE_ACCELERATOR": "cuda"}):
            self.assertEqual(accelerator.accelerator_kind(), "cuda")
            self.assertFalse(accelerator.is_cpu_profile())
            self.assertTrue(accelerator.colmap_use_gpu())

    def test_cpu_colmap_defaults(self) -> None:
        with mock.patch.dict(os.environ, {"MURAVEI_FORCE_ACCELERATOR": "cpu"}, clear=False):
            os.environ.pop("COLMAP_MAX_IMAGE_SIZE", None)
            os.environ.pop("COLMAP_MAX_FRAMES", None)
            self.assertEqual(recon_colmap.max_image_size(), CPU_COLMAP_MAX_IMAGE_SIZE)
            self.assertEqual(recon_colmap.max_frames(), CPU_COLMAP_MAX_FRAMES)

    def test_cpu_dense_disabled_default(self) -> None:
        with mock.patch.dict(os.environ, {"MURAVEI_FORCE_ACCELERATOR": "cpu"}):
            os.environ.pop("MURAVEI_CPU_DISABLE_DENSE", None)
            self.assertTrue(accelerator.cpu_dense_mesh_disabled())

    def test_cpu_dense_allow_flag(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"MURAVEI_FORCE_ACCELERATOR": "cpu", "MURAVEI_CPU_DISABLE_DENSE": "0"},
        ):
            self.assertFalse(accelerator.cpu_dense_mesh_disabled())

    def test_gsplat_reason_on_cpu_presets(self) -> None:
        from services import train_presets

        with mock.patch.dict(os.environ, {"MURAVEI_FORCE_ACCELERATOR": "cpu"}):
            with mock.patch(
                "services.alicevision.alicevision_available", return_value=True
            ), mock.patch(
                "services.alicevision.alicevision_cuda_ready", return_value=(False, "no cuda")
            ), mock.patch(
                "services.gsplat_msvc.gsplat_train_ready", return_value=(True, "")
            ):
                items = {i["id"]: i for i in train_presets.presets_for_client()}
                splat = items.get("splat") or items.get("balanced")
                self.assertIsNotNone(splat)
                assert splat is not None
                self.assertTrue(splat["disabled"])
                self.assertIn(GSPLAT_CUDA_REASON_RU, splat["disabled_reason"])
                dense = items.get("dense")
                if dense:
                    self.assertTrue(dense["disabled"])
                    self.assertIn("CPU", dense["disabled_reason"])


if __name__ == "__main__":
    unittest.main()
