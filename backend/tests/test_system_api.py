"""Unit tests for GET /api/system/hardware VRAM fields (mocked GPU)."""
from __future__ import annotations

import asyncio
import types
import unittest
from unittest import mock

# Import app first to avoid api.system ↔ main circular import.
from main import app  # noqa: F401
from api import system as system_api


class HardwareVramTests(unittest.TestCase):
    def test_pynvml_path_reports_gb(self) -> None:
        mem = types.SimpleNamespace(total=8 * 1024**3, used=2 * 1024**3, free=6 * 1024**3)
        fake_pynvml = types.SimpleNamespace(
            NVML_TEMPERATURE_GPU=0,
            nvmlInit=mock.Mock(),
            nvmlShutdown=mock.Mock(),
            nvmlDeviceGetHandleByIndex=mock.Mock(return_value="h0"),
            nvmlDeviceGetMemoryInfo=mock.Mock(return_value=mem),
            nvmlDeviceGetTemperature=mock.Mock(return_value=42),
            nvmlDeviceGetName=mock.Mock(return_value=b"FakeGPU"),
        )
        with mock.patch.dict("sys.modules", {"pynvml": fake_pynvml}):
            with mock.patch("api.system.hardware_spec", return_value={"cpu": "test"}):
                with mock.patch.object(system_api, "_sim", {"active": None}):
                    out = asyncio.run(system_api.hardware(_user={"role": "operator"}))
        self.assertEqual(out["gpu_name"], "FakeGPU")
        self.assertEqual(out["vram_total_mb"], 8192)
        self.assertEqual(out["vram_used_mb"], 2048)
        self.assertEqual(out["vram_free_mb"], 6144)
        self.assertAlmostEqual(out["vram_total_gb"], 8.0)
        self.assertAlmostEqual(out["vram_used_gb"], 2.0)
        self.assertAlmostEqual(out["vram_free_gb"], 6.0)
        self.assertEqual(out["gpu_temp_c"], 42)

    def test_torch_cuda_fallback(self) -> None:
        class _Boom:
            def __getattr__(self, name: str):  # noqa: ANN001
                raise RuntimeError("no nvml")

        fake_torch = types.SimpleNamespace(
            cuda=types.SimpleNamespace(
                is_available=mock.Mock(return_value=True),
                mem_get_info=mock.Mock(return_value=(3 * 1024**3, 10 * 1024**3)),
                get_device_name=mock.Mock(return_value="TorchGPU"),
            )
        )
        with mock.patch.dict("sys.modules", {"pynvml": _Boom(), "torch": fake_torch}):
            with mock.patch("api.system.hardware_spec", return_value={}):
                with mock.patch.object(system_api, "_sim", {"active": None}):
                    out = asyncio.run(system_api.hardware(_user={"role": "operator"}))
        self.assertEqual(out["gpu_name"], "TorchGPU")
        self.assertEqual(out["vram_total_mb"], 10240)
        self.assertEqual(out["vram_free_mb"], 3072)
        self.assertAlmostEqual(out["vram_free_gb"], 3.0)

    def test_cpu_when_no_cuda(self) -> None:
        class _Boom:
            def __getattr__(self, name: str):  # noqa: ANN001
                raise RuntimeError("no nvml")

        fake_torch = types.SimpleNamespace(
            cuda=types.SimpleNamespace(is_available=mock.Mock(return_value=False))
        )
        with mock.patch.dict("sys.modules", {"pynvml": _Boom(), "torch": fake_torch}):
            with mock.patch("api.system.hardware_spec", return_value={}):
                with mock.patch.object(system_api, "_sim", {"active": None}):
                    out = asyncio.run(system_api.hardware(_user={"role": "operator"}))
        self.assertEqual(out["gpu_name"], "CPU")
        self.assertEqual(out["vram_total_mb"], 0)
        self.assertEqual(out["vram_free_gb"], 0.0)


if __name__ == "__main__":
    unittest.main()
