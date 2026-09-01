"""Local hardware snapshot for support ZIP and HTML reports."""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

from main import BASE_DIR


def hardware_spec() -> dict[str, Any]:
    spec: dict[str, Any] = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version,
        "base_dir": str(BASE_DIR),
    }
    try:
        import psutil

        vm = psutil.virtual_memory()
        spec["cpu_count"] = psutil.cpu_count()
        spec["cpu_percent"] = psutil.cpu_percent(interval=0.15)
        spec["ram_total_mb"] = int(vm.total / (1024 * 1024))
        spec["ram_available_mb"] = int(vm.available / (1024 * 1024))
        spec["disks"] = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except OSError:
                continue
            spec["disks"].append(
                {
                    "device": part.device,
                    "mount": part.mountpoint,
                    "total_gb": round(usage.total / (1024**3), 1),
                    "free_gb": round(usage.free / (1024**3), 1),
                }
            )
    except Exception as exc:  # noqa: BLE001
        spec["psutil_error"] = str(exc)

    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        try:
            result = subprocess.run(
                [
                    nvidia,
                    "--query-gpu=name,memory.total,memory.used,driver_version",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            spec["gpu"] = (result.stdout or result.stderr or "").strip()
        except Exception as exc:  # noqa: BLE001
            spec["gpu_error"] = str(exc)
    else:
        spec["gpu"] = "nvidia-smi not found"
    return spec
