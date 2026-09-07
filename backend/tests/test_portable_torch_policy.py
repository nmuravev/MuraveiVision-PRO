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
        # FullKit cuda picks opposite
        sel_cuda, rej_cuda = self.pol.filter_torch_wheels(names, want_cuda_flag=True)
        self.assertTrue(all("+cu128" in s for s in sel_cuda))
        self.assertTrue(any("+cpu" in r for r in rej_cuda))

    def test_cuda_only_cache_mini_selects_empty(self):
        names = [
            "torch-2.6.0+cu128-cp312-cp312-win_amd64.whl",
            "torchvision-0.21.0+cu128-cp312-cp312-win_amd64.whl",
            "fastapi-0.141.1-py3-none-any.whl",
        ]
        selected = self.pol.select_torch_wheels_or_refuse(names, want_cuda_flag=False)
        self.assertEqual(selected, [])
        # Must not accidentally return CUDA wheels
        for n in names:
            if self.pol.is_torch_family_wheel(n):
                self.assertFalse(self.pol.wheel_matches_policy(n, False))

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


if __name__ == "__main__":
    unittest.main()
