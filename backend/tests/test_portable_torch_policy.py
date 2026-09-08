"""Unit tests for profile-driven portable torch wheel selection."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


def _load_policy():
    path = Path(__file__).resolve().parents[2] / "scripts" / "portable_torch_policy.py"
    spec = importlib.util.spec_from_file_location("portable_torch_policy", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestPortableTorchPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pol = _load_policy()

    def test_policy_loaded_via_importlib(self):
        self.assertTrue(hasattr(self.pol, "want_cuda"))
        self.assertTrue(hasattr(self.pol, "select_torch_wheels_or_refuse"))
        self.assertTrue(hasattr(self.pol, "policy_dict"))
        self.assertIn("/cpu", self.pol.PYTORCH_CPU_INDEX)
        self.assertIn("cu128", self.pol.PYTORCH_CU128_INDEX)

    def test_mini_always_cpu(self):
        self.assertFalse(self.pol.want_cuda("mini", "cuda"))
        self.assertFalse(self.pol.want_cuda("Mini", "cpu"))
        self.assertFalse(self.pol.want_cuda("NoDetectWeights", "cuda"))
        p = self.pol.policy_dict("mini", "cuda")
        self.assertTrue(p["assert_cuda_is_none"])
        self.assertIn("/cpu", p["index_url"])

    def test_lite_always_cpu(self):
        self.assertFalse(self.pol.want_cuda("lite", "cuda"))
        self.assertIn("/cpu", self.pol.index_url("lite", "cuda"))

    def test_fullkit_cuda_and_cpu(self):
        self.assertTrue(self.pol.want_cuda("fullkit", "cuda"))
        self.assertFalse(self.pol.want_cuda("fullkit", "cpu"))
        self.assertIn("cu128", self.pol.index_url("full", "cuda"))
        self.assertIn("/cpu", self.pol.index_url("fullkit", "cpu"))

    def test_mixed_cache_mini_never_picks_cuda(self):
        names = [
            "numpy-1.26.4-cp312-cp312-win_amd64.whl",
            "torch-2.6.0+cu128-cp312-cp312-win_amd64.whl",
            "torchvision-0.21.0+cu128-cp312-cp312-win_amd64.whl",
            "torch-2.6.0+cpu-cp312-cp312-win_amd64.whl",
            "torchvision-0.21.0+cpu-cp312-cp312-win_amd64.whl",
            "ultralytics-8.4.143-py3-none-any.whl",
        ]
        selected, rejected = self.pol.filter_torch_wheels(names, want_cuda_flag=False)
        self.assertTrue(all("+cpu" in s for s in selected))
        self.assertTrue(any("+cu128" in r for r in rejected))
        self.assertFalse(any("+cu" in s for s in selected))

    def test_mixed_cache_fullkit_selects_cuda(self):
        """Mock cache with CPU+CUDA + kit=full → selects CUDA only."""
        names = [
            "torch-2.6.0+cu128-cp312-cp312-win_amd64.whl",
            "torchvision-0.21.0+cu128-cp312-cp312-win_amd64.whl",
            "torch-2.6.0+cpu-cp312-cp312-win_amd64.whl",
            "torchvision-0.21.0+cpu-cp312-cp312-win_amd64.whl",
        ]
        self.assertTrue(self.pol.want_cuda("fullkit", "cuda"))
        selected, rejected = self.pol.filter_torch_wheels(names, want_cuda_flag=True)
        self.assertTrue(all("+cu128" in s for s in selected))
        self.assertTrue(any("+cpu" in r for r in rejected))
        self.assertEqual(len(selected), 2)
        pol = self.pol.policy_dict("fullkit", "cuda")
        self.assertFalse(pol["assert_cuda_is_none"])
        self.assertIn("cu128", pol["index_url"])

    def test_cuda_only_cache_mini_refuses_and_cpu_index(self):
        """CUDA-only cache + kit=mini → empty selection; fallback index is CPU."""
        names = [
            "torch-2.6.0+cu128-cp312-cp312-win_amd64.whl",
            "torchvision-0.21.0+cu128-cp312-cp312-win_amd64.whl",
            "fastapi-0.141.1-py3-none-any.whl",
        ]
        selected = self.pol.select_torch_wheels_or_refuse(names, want_cuda_flag=False)
        self.assertEqual(selected, [])
        for n in names:
            if self.pol.is_torch_family_wheel(n):
                self.assertFalse(self.pol.wheel_matches_policy(n, False))
        # Online fallback for Mini must be CPU index (never cu*)
        self.assertEqual(self.pol.index_url("mini", "cuda"), self.pol.PYTORCH_CPU_INDEX)
        pol = self.pol.policy_dict("mini", "cuda")
        self.assertTrue(pol["assert_cuda_is_none"])
        self.assertIn("/cpu", pol["index_url"])

    def test_cpu_only_cache_fullkit_falls_back_to_cuda_index(self):
        """CPU-only cache + kit=full → empty selection; fallback index is CUDA."""
        names = [
            "torch-2.6.0+cpu-cp312-cp312-win_amd64.whl",
            "torchvision-0.21.0+cpu-cp312-cp312-win_amd64.whl",
            "numpy-1.26.4-cp312-cp312-win_amd64.whl",
        ]
        selected = self.pol.select_torch_wheels_or_refuse(names, want_cuda_flag=True)
        self.assertEqual(selected, [])
        for n in names:
            if self.pol.is_torch_family_wheel(n):
                self.assertFalse(self.pol.wheel_matches_policy(n, True))
        self.assertEqual(self.pol.index_url("fullkit", "cuda"), self.pol.PYTORCH_CU128_INDEX)
        pol = self.pol.policy_dict("fullkit", "cuda")
        self.assertFalse(pol["assert_cuda_is_none"])
        self.assertIn("cu128", pol["index_url"])

    def test_post_stage_assert_flags(self):
        """Post-stage assert logic: Mini/Lite → cuda is None; FullKit cuda → not None."""
        mini = self.pol.policy_dict("mini", "cuda")
        lite = self.pol.policy_dict("lite", "cuda")
        full = self.pol.policy_dict("fullkit", "cuda")
        full_cpu = self.pol.policy_dict("fullkit", "cpu")
        self.assertTrue(mini["assert_cuda_is_none"])
        self.assertTrue(lite["assert_cuda_is_none"])
        self.assertFalse(full["assert_cuda_is_none"])
        self.assertTrue(full_cpu["assert_cuda_is_none"])

    def test_cli_cache_mismatch_exit(self):
        rc = self.pol.main(
            [
                "--kit",
                "mini",
                "--flavor",
                "cuda",
                "--list-wheels",
                "torch-2.6.0+cu128-cp312-cp312-win_amd64.whl",
                "--json",
            ]
        )
        self.assertEqual(rc, 2)

    def test_cli_fullkit_cpu_only_cache_mismatch(self):
        rc = self.pol.main(
            [
                "--kit",
                "fullkit",
                "--flavor",
                "cuda",
                "--list-wheels",
                "torch-2.6.0+cpu-cp312-cp312-win_amd64.whl",
                "--json",
            ]
        )
        self.assertEqual(rc, 2)

    def test_unmarked_pypi_torch_not_cpu(self):
        """Unmarked PyPI torch must not count as CPU (often CUDA on Windows)."""
        unmarked = "torch-2.14.0-cp312-cp312-win_amd64.whl"
        self.assertTrue(self.pol.is_torch_family_wheel(unmarked))
        self.assertFalse(self.pol.is_cuda_variant_wheel(unmarked))
        self.assertFalse(self.pol.is_cpu_variant_wheel(unmarked))
        self.assertFalse(self.pol.wheel_matches_policy(unmarked, False))
        self.assertFalse(self.pol.wheel_matches_policy(unmarked, True))


if __name__ == "__main__":
    unittest.main()
