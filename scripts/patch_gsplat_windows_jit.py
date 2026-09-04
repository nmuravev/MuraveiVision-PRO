"""Patch installed gsplat cuda/_backend.py for Windows MSVC JIT.

PyPI gsplat is source-only; first rasterize JIT-compiles CUDA. On Windows:
- MSVC rejects GCC flag -Wno-attributes
- Windows SDK rpcndr.h `#define small char` breaks torch CUDACachingAllocator.h

Run after: pip install gsplat
  muravei_env\\Scripts\\python.exe scripts\\patch_gsplat_windows_jit.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "muravei_env" / "Lib" / "site-packages" / "gsplat" / "cuda" / "_backend.py"

OLD = (
    '        extra_include_paths = [os.path.join(PATH, "include/"), glm_path]\n'
    '        opt_level = "-O0" if FAST_COMPILE else "-O3"\n'
    '        extra_cflags = [opt_level, "-Wno-attributes"]\n'
    '        extra_cuda_cflags = [opt_level]\n'
    '        if not NO_FAST_MATH:\n'
    '            extra_cuda_cflags += ["-use_fast_math"]\n'
)

NEW = (
    '        extra_include_paths = [os.path.join(PATH, "include/"), glm_path]\n'
    '        # MuraveiVision PRO: MSVC needs WIN32_LEAN_AND_MEAN; no GCC -Wno-attributes\n'
    '        if os.name == "nt":\n'
    '            opt_level = "/Od" if FAST_COMPILE else "/O2"\n'
    '            extra_cflags = [opt_level, "/DWIN32_LEAN_AND_MEAN", "/Usmall"]\n'
    '            cuda_opt = "-O0" if FAST_COMPILE else "-O3"\n'
    '            extra_cuda_cflags = [\n'
    '                cuda_opt,\n'
    '                "-allow-unsupported-compiler",\n'
    '                "-DWIN32_LEAN_AND_MEAN",\n'
    '                "-Usmall",\n'
    '            ]\n'
    '        else:\n'
    '            opt_level = "-O0" if FAST_COMPILE else "-O3"\n'
    '            extra_cflags = [opt_level, "-Wno-attributes"]\n'
    '            extra_cuda_cflags = [opt_level]\n'
    '        if not NO_FAST_MATH:\n'
    '            extra_cuda_cflags += ["-use_fast_math"]\n'
)


def main() -> int:
    if not BACKEND.is_file():
        print(f"missing {BACKEND}", file=sys.stderr)
        return 2
    text = BACKEND.read_text(encoding="utf-8")
    if "MuraveiVision PRO: MSVC needs WIN32_LEAN_AND_MEAN" in text:
        print("already patched")
        return 0
    if OLD not in text:
        print("pattern not found — gsplat version changed?", file=sys.stderr)
        return 1
    BACKEND.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print(f"patched {BACKEND}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
