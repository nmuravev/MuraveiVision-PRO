"""AliceVision sidecar discovery (optional dense MVS / mesh).

Resolves binaries under ``sidecars/alicevision/<platform>/`` or
``ALICEVISION_ROOT`` (points at the platform root that contains ``bin/``).
Never downloads weights at runtime — use ``scripts/alicevision_manifest.json``
and fetch scripts offline.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import sys
from functools import lru_cache
from pathlib import Path

from services.security import BASE_DIR

_LOG = logging.getLogger("muravei.alicevision")
_MANIFEST = BASE_DIR / "scripts" / "alicevision_manifest.json"
_SIDECAR = BASE_DIR / "sidecars" / "alicevision"

_logged_version = False


def _platform_dir_name() -> str:
    if sys.platform.startswith("win"):
        return "windows-x64"
    if sys.platform == "darwin" and platform.machine().lower() in ("arm64", "aarch64"):
        return "macos-arm64"
    if sys.platform.startswith("linux"):
        return "linux-x64"
    return "windows-x64"


def alicevision_root() -> Path | None:
    """Return AliceVision install root (contains ``bin/``) or None."""
    env = (os.environ.get("ALICEVISION_ROOT") or "").strip()
    if env:
        root = Path(env)
        if (root / "bin").is_dir() or root.is_dir():
            return root.resolve()
        return None
    candidate = _SIDECAR / _platform_dir_name()
    if (candidate / "bin").is_dir():
        return candidate.resolve()
    if candidate.is_dir() and any(candidate.glob("aliceVision_*")):
        return candidate.resolve()
    return None


def alicevision_bin_dir(root: Path | None = None) -> Path | None:
    root = root or alicevision_root()
    if root is None:
        return None
    bin_dir = root / "bin"
    if bin_dir.is_dir():
        return bin_dir
    if any(root.glob("aliceVision_*")):
        return root
    return None


def _exe_name(tool: str) -> str:
    name = tool.strip()
    if name.startswith("aliceVision_"):
        base = name
    else:
        base = f"aliceVision_{name}"
    if sys.platform.startswith("win") and not base.lower().endswith(".exe"):
        return f"{base}.exe"
    if base.lower().endswith(".exe") and not sys.platform.startswith("win"):
        return base[:-4]
    return base


def alicevision_bin(tool: str) -> Path:
    """Resolve ``aliceVision_<tool>`` path; raises FileNotFoundError if missing."""
    bin_dir = alicevision_bin_dir()
    if bin_dir is None:
        raise FileNotFoundError(
            "AliceVision sidecar not found. Set ALICEVISION_ROOT or stage "
            "sidecars/alicevision/<platform>/bin (see scripts/alicevision_manifest.json)."
        )
    path = bin_dir / _exe_name(tool)
    if not path.is_file():
        raise FileNotFoundError(f"AliceVision tool missing: {path.name}")
    return path


def alicevision_available() -> bool:
    try:
        # prepareDenseScene is required for dense/mesh presets
        alicevision_bin("prepareDenseScene")
        return True
    except FileNotFoundError:
        return False


def _manifest_version() -> str | None:
    if not _MANIFEST.is_file():
        return None
    try:
        data = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    chosen = data.get("chosen") if isinstance(data, dict) else None
    if isinstance(chosen, dict):
        ver = chosen.get("version")
        if ver:
            return str(ver)
    return None


def alicevision_version() -> str | None:
    """Best-effort version from staged manifest (no network)."""
    return _manifest_version()


def alicevision_cuda_ready() -> tuple[bool, str]:
    """Depth maps need NVIDIA CUDA in shipping AliceVision builds."""
    try:
        import torch

        if torch.cuda.is_available():
            return True, ""
        return False, "AliceVision dense/mesh требует NVIDIA CUDA (нет CPU fallback)"
    except Exception:  # noqa: BLE001
        return False, "AliceVision dense/mesh требует NVIDIA CUDA (torch/CUDA недоступны)"


def log_first_use() -> None:
    """Emit one runtime line when AliceVision is first resolved."""
    global _logged_version
    if _logged_version:
        return
    if not alicevision_available():
        return
    ver = alicevision_version() or "unknown"
    msg = f"Using AliceVision v{ver} (MPL-2.0)"
    _LOG.info(msg)
    try:
        from services.runtime_log import write as runtime_write

        runtime_write("info", "alicevision", msg)
    except Exception:  # noqa: BLE001
        pass
    _logged_version = True


@lru_cache(maxsize=1)
def alicevision_env() -> dict[str, str]:
    """Env overlay so CLIs find OCIO under share/aliceVision."""
    root = alicevision_root()
    if root is None:
        return {}
    out = {"ALICEVISION_ROOT": str(root)}
    ocio = root / "share" / "aliceVision" / "config.ocio"
    if ocio.is_file():
        out["OCIO"] = str(ocio)
    return out


def clear_caches() -> None:
    """Test helper — reset first-use log + env cache."""
    global _logged_version
    _logged_version = False
    alicevision_env.cache_clear()
