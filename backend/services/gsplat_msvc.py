"""Discover MSVC/CUDA for gsplat CUDA JIT on Windows (no host-hardcoded paths)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from services.security import BASE_DIR

MSVC_NEED_MSG = (
    "Нужен MSVC 14.44 (см. ENGINEER_GUIDE) или пресет Bootstrap"
)

_VCVARS_CACHE: Path | None | bool = False  # False=unset, None=missing, Path=found
_CUDA_CACHE: Path | None | bool = False


def cl_on_path() -> bool:
    return shutil.which("cl") is not None or shutil.which("cl.exe") is not None


def find_vcvars64() -> Path | None:
    """Locate vcvars64.bat via env, vswhere, or VS install tree under Program Files."""
    global _VCVARS_CACHE
    if _VCVARS_CACHE is not False:
        return _VCVARS_CACHE if isinstance(_VCVARS_CACHE, Path) else None

    for key in ("MURAVEI_VCVARS64", "VCVARS64"):
        raw = (os.environ.get(key) or "").strip().strip('"')
        if raw:
            p = Path(raw)
            if p.is_file():
                _VCVARS_CACHE = p
                return p

    vswhere = (
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Microsoft Visual Studio"
        / "Installer"
        / "vswhere.exe"
    )
    if vswhere.is_file():
        try:
            out = subprocess.run(
                [
                    str(vswhere),
                    "-latest",
                    "-products",
                    "*",
                    "-requires",
                    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                    "-find",
                    r"VC\Auxiliary\Build\vcvars64.bat",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            line = (out.stdout or "").strip().splitlines()
            if line:
                p = Path(line[0].strip())
                if p.is_file():
                    _VCVARS_CACHE = p
                    return p
        except (OSError, subprocess.TimeoutExpired):
            pass

    roots: list[Path] = []
    for key in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(key)
        if base:
            roots.append(Path(base) / "Microsoft Visual Studio")

    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for edition in ("BuildTools", "Community", "Professional", "Enterprise"):
            for p in root.glob(f"*/{edition}/VC/Auxiliary/Build/vcvars64.bat"):
                if p.is_file():
                    found.append(p)

    def _rank(p: Path) -> tuple[int, str]:
        # Prefer version folder "18" (VS 2026 Build Tools) then lexical newest
        try:
            ver = p.parts[p.parts.index("Microsoft Visual Studio") + 1]
        except (ValueError, IndexError):
            ver = ""
        prefer = 0 if ver == "18" else 1
        return (prefer, ver)

    if found:
        found.sort(key=_rank)
        _VCVARS_CACHE = found[0]
        return found[0]

    _VCVARS_CACHE = None
    return None


def find_cuda_home() -> Path | None:
    global _CUDA_CACHE
    if _CUDA_CACHE is not False:
        return _CUDA_CACHE if isinstance(_CUDA_CACHE, Path) else None

    for key in ("CUDA_HOME", "CUDA_PATH", "MURAVEI_CUDA_HOME"):
        raw = (os.environ.get(key) or "").strip().strip('"')
        if not raw:
            continue
        p = Path(raw)
        if (p / "bin" / "nvcc.exe").is_file() or (p / "bin" / "nvcc").is_file():
            _CUDA_CACHE = p
            return p

    toolkit = (
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "NVIDIA GPU Computing Toolkit"
        / "CUDA"
    )
    if toolkit.is_dir():
        versions = [d for d in toolkit.iterdir() if d.is_dir() and d.name.startswith("v")]
        # Prefer 12.8, else highest version name
        preferred = toolkit / "v12.8"
        if (preferred / "bin" / "nvcc.exe").is_file():
            _CUDA_CACHE = preferred
            return preferred
        versions.sort(key=lambda d: d.name, reverse=True)
        for d in versions:
            if (d / "bin" / "nvcc.exe").is_file():
                _CUDA_CACHE = d
                return d

    _CUDA_CACHE = None
    return None


def python_include_dir() -> Path | None:
    """Headers matching the running interpreter (venv → base_prefix)."""
    candidates = [
        Path(sys.base_prefix) / "Include",
        Path(sys.prefix) / "Include",
    ]
    env = (os.environ.get("MURAVEI_PYTHON_INCLUDE") or "").strip().strip('"')
    if env:
        candidates.insert(0, Path(env))
    for p in candidates:
        if p.is_dir() and (p / "Python.h").is_file():
            return p
    return None


def gsplat_train_ready() -> tuple[bool, str]:
    """Whether Balanced/High (gsplat JIT) can run on this host."""
    if os.name != "nt":
        # Non-Windows: assume system compiler available if present
        if shutil.which("c++") or shutil.which("g++") or shutil.which("clang++"):
            return True, ""
        return False, MSVC_NEED_MSG
    if cl_on_path():
        return True, ""
    if find_vcvars64() is not None:
        return True, ""
    return False, MSVC_NEED_MSG


def clear_caches() -> None:
    """Test helper."""
    global _VCVARS_CACHE, _CUDA_CACHE
    _VCVARS_CACHE = False
    _CUDA_CACHE = False


def build_gsplat_launch(
    python: str,
    script_args: list[str],
    *,
    cwd: Path | None = None,
) -> tuple[list[str], dict[str, str] | None]:
    """Return (cmd, env) to run gsplat under MSVC when needed.

    On Windows without ``cl`` on PATH but with vcvars: launch via a temp .bat
    that calls vcvars64 -vcvars_ver=14.44 then python.
    """
    work = cwd or BASE_DIR
    env = os.environ.copy()
    cuda = find_cuda_home()
    if cuda:
        env["CUDA_HOME"] = str(cuda)
        env["CUDA_PATH"] = str(cuda)
        env["PATH"] = str(cuda / "bin") + os.pathsep + env.get("PATH", "")
    env.setdefault("TORCH_CUDA_ARCH_LIST", os.environ.get("TORCH_CUDA_ARCH_LIST", "12.0"))
    lean = "-allow-unsupported-compiler -DWIN32_LEAN_AND_MEAN -Usmall"
    env.setdefault("TORCH_NVCC_FLAGS", lean)
    env.setdefault("NVCC_PREPEND_FLAGS", lean)
    env["PYTHONPATH"] = "backend" + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )

    py_args = [python, *script_args]
    if os.name != "nt" or cl_on_path():
        return py_args, env

    vcvars = find_vcvars64()
    if vcvars is None:
        raise RuntimeError(MSVC_NEED_MSG)

    py_inc = python_include_dir()
    # Quote for cmd
    def q(s: str) -> str:
        return '"' + s.replace('"', "") + '"'

    arg_line = " ".join(q(a) for a in py_args)
    lines = [
        "@echo off",
        f"call {q(str(vcvars))} -vcvars_ver=14.44",
    ]
    if cuda:
        lines.append(f'set "CUDA_HOME={cuda}"')
        lines.append('set "CUDA_PATH=%CUDA_HOME%"')
        lines.append('set "PATH=%CUDA_HOME%\\bin;%PATH%"')
    if py_inc:
        lines.append(f'set "INCLUDE={py_inc};%INCLUDE%"')
    lines.extend(
        [
            f'set "TORCH_CUDA_ARCH_LIST={env["TORCH_CUDA_ARCH_LIST"]}"',
            f'set "TORCH_NVCC_FLAGS={lean}"',
            f'set "NVCC_PREPEND_FLAGS={lean}"',
            f"cd /d {q(str(work))}",
            "set PYTHONPATH=backend",
            arg_line,
            "exit /b %ERRORLEVEL%",
        ]
    )
    fd, bat_path = tempfile.mkstemp(prefix="muravei_gsplat_", suffix=".bat")
    os.close(fd)
    Path(bat_path).write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")
    return ["cmd", "/c", bat_path], env
