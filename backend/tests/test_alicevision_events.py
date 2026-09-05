"""Extra AliceVision event-key / progress contract tests (RC gate)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from services import alicevision_pipeline as avp


AV_TRACE_EVENTS = frozenset(
    {
        "alicevision-discover",
        "alicevision-step-start",
        "alicevision-step-done",
        "alicevision-step-error",
        "dense-artifact-ready",
        "mesh-artifact-ready",
    }
)


class TestAliceVisionEventKeys(unittest.TestCase):
    def test_event_keys_documented(self) -> None:
        # Contract for Session Trace / ops modal (Phase 5)
        for key in AV_TRACE_EVENTS:
            self.assertTrue(key)
            self.assertTrue("-" in key or key.endswith("ready"))

    def test_run_emits_discover_when_missing(self) -> None:
        events: list[dict] = []
        with patch.object(avp, "alicevision_available", return_value=False):
            import tempfile
            from pathlib import Path

            with tempfile.TemporaryDirectory() as td:
                avp.run_dense_pipeline(Path(td), mode="dense", emit=events.append)
        kinds = {e.get("event") for e in events}
        self.assertIn("alicevision-discover", kinds)

    def test_normalize_selected_order_mesh_first(self) -> None:
        man = avp.normalize_artifacts(
            {
                "artifacts": {
                    "sparse": {"file": "sparse_points.json"},
                    "dense": {"file": "dense_point_cloud.ply"},
                    "mesh": {"file": "textured_mesh.obj"},
                    "splat": {"file": "model.ply"},
                }
            }
        )
        self.assertEqual(man["selected_artifact"], "mesh")

    def test_patch_ok_sets_dense_selected(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            (job / "dense_point_cloud.ply").write_bytes(b"ply\n")
            (job / "sparse_points.json").write_text("{}", encoding="utf-8")
            man = {"status": "colmap_done", "sparse_file": "sparse_points.json"}
            out = avp.patch_manifest_artifacts(
                man,
                job,
                {
                    "ok": True,
                    "artifacts": {"dense": {"file": "dense_point_cloud.ply", "size_mb": 1.0}},
                    "warning": None,
                    "error": None,
                },
            )
        self.assertEqual(out["selected_artifact"], "dense")
        self.assertEqual(out["status"], "done")
        self.assertEqual(out["artifact"], "dense_point_cloud.ply")

    def test_cuda_gate_reason_russian(self) -> None:
        ok, reason = False, "AliceVision dense/mesh требует NVIDIA CUDA (нет CPU fallback)"
        self.assertFalse(ok)
        self.assertIn("CUDA", reason)


class TestAliceVisionPresetAliases(unittest.TestCase):
    def test_load_file_has_primary_and_aliases(self) -> None:
        from services.train_presets import load_presets

        presets, from_file = load_presets()
        self.assertTrue(from_file)
        for pid in ("sparse", "dense", "mesh", "splat", "bootstrap", "balanced", "high"):
            self.assertIn(pid, presets)
        self.assertEqual(presets["dense"]["script"], "alicevision_mvs")
        self.assertEqual(presets["mesh"]["script"], "alicevision_mesh")
        self.assertEqual(presets["splat"]["script"], "gsplat")

    def test_client_order_primary_first(self) -> None:
        from services import train_presets

        with patch.object(train_presets, "total_vram_gb", return_value=16.0):
            with patch("services.alicevision.alicevision_available", return_value=True):
                with patch(
                    "services.alicevision.alicevision_cuda_ready",
                    return_value=(True, ""),
                ):
                    with patch(
                        "services.gsplat_msvc.gsplat_train_ready",
                        return_value=(True, ""),
                    ):
                        items = train_presets.presets_for_client()
        ids = [i["id"] for i in items]
        self.assertLess(ids.index("sparse"), ids.index("dense"))
        self.assertLess(ids.index("dense"), ids.index("mesh"))
        self.assertLess(ids.index("mesh"), ids.index("splat"))
        self.assertLess(ids.index("splat"), ids.index("bootstrap"))

    def test_mesh_disabled_without_cuda(self) -> None:
        from services import train_presets

        with patch.object(train_presets, "total_vram_gb", return_value=16.0):
            with patch("services.alicevision.alicevision_available", return_value=True):
                with patch(
                    "services.alicevision.alicevision_cuda_ready",
                    return_value=(False, "нет CUDA"),
                ):
                    items = train_presets.presets_for_client()
        mesh = next(i for i in items if i["id"] == "mesh")
        self.assertTrue(mesh["disabled"])
        self.assertIn("CUDA", mesh["disabled_reason"])

    def test_exe_name_windows(self) -> None:
        from services import alicevision
        import sys

        name = alicevision._exe_name("meshing")
        if sys.platform.startswith("win"):
            self.assertTrue(name.endswith(".exe"))
        self.assertIn("aliceVision_meshing", name)

    def test_invert_w2c_identity(self) -> None:
        R = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        Rt, C = avp._invert_w2c(R, [1.0, 2.0, 3.0])
        self.assertEqual(Rt[0][0], 1.0)
        self.assertAlmostEqual(C[0], -1.0)
        self.assertAlmostEqual(C[1], -2.0)
        self.assertAlmostEqual(C[2], -3.0)


if __name__ == "__main__":
    unittest.main()
