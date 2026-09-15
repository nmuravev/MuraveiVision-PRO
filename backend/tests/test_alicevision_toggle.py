"""P8: alicevision_enabled engineer toggle greys Mesh preset."""
from __future__ import annotations

import unittest
from unittest.mock import patch


class TestAliceVisionEngineerToggle(unittest.TestCase):
    def test_mesh_disabled_when_alicevision_enabled_off(self) -> None:
        from services import train_presets

        with patch.object(train_presets, "total_vram_gb", return_value=24.0):
            with patch("services.accelerator.is_cpu_profile", return_value=False):
                with patch("services.accelerator.cpu_dense_mesh_disabled", return_value=False):
                    with patch("services.alicevision.alicevision_available", return_value=True):
                        with patch(
                            "services.alicevision.alicevision_cuda_ready",
                            return_value=(True, ""),
                        ):
                            with patch(
                                "services.gsplat_msvc.gsplat_train_ready",
                                return_value=(True, ""),
                            ):
                                with patch(
                                    "services.db.get_setting",
                                    side_effect=lambda k, default=None: (
                                        "0" if k == "alicevision_enabled" else default
                                    ),
                                ):
                                    items = train_presets.presets_for_client()

        mesh = next(p for p in items if p["id"] == "mesh")
        self.assertTrue(mesh["disabled"])
        self.assertIn("отключён инженером", mesh["disabled_reason"])

        # AV-dense hidden by default (no legacy env)
        self.assertFalse(any(p["id"] == "dense" for p in items))

    def test_legacy_av_dense_visible_with_env(self) -> None:
        from services import train_presets

        with patch.dict("os.environ", {"MURAVEI_LEGACY_AV_DENSE": "1"}):
            with patch.object(train_presets, "total_vram_gb", return_value=24.0):
                with patch("services.accelerator.is_cpu_profile", return_value=False):
                    with patch("services.accelerator.cpu_dense_mesh_disabled", return_value=False):
                        with patch("services.alicevision.alicevision_available", return_value=True):
                            with patch(
                                "services.alicevision.alicevision_cuda_ready",
                                return_value=(True, ""),
                            ):
                                with patch(
                                    "services.gsplat_msvc.gsplat_train_ready",
                                    return_value=(True, ""),
                                ):
                                    with patch(
                                        "services.db.get_setting",
                                        side_effect=lambda k, default=None: (
                                            "1" if k == "alicevision_enabled" else default
                                        ),
                                    ):
                                        items = train_presets.presets_for_client()

        self.assertTrue(any(p["id"] == "dense" for p in items))


if __name__ == "__main__":
    unittest.main()
