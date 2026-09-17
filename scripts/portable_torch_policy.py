#!/usr/bin/env python3
"""Profile-driven torch wheel selection for MuraveiVision portable kits.

Mini/Lite → CPU only. FullKit → CUDA (cu*) unless TorchFlavor=cpu.
Keeps both wheel variants in cache; selection is by profile, never \"first found\".
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Iterable, List, Sequence

# CUDA local-version / tag markers commonly seen on PyTorch wheels
_CUDA_MARK = re.compile(r"(?:\+cu|cu1[12]\d|cuda)", re.IGNORECASE)
_CPU_MARK = re.compile(r"\+cpu", re.IGNORECASE)
_TORCH_FAMILY = re.compile(r"^(torch|torchvision|torchaudio)-", re.IGNORECASE)

PYTORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
PYTORCH_CU128_INDEX = "https://download.pytorch.org/whl/cu128"


def normalize_kit(kit: str) -> str:
    k = (kit or "").strip().lower()
    aliases = {
        "mini": "mini",
        "nodetectweights": "mini",
        "no_detect_weights": "mini",
        "lite": "lite",
        "portable": "lite",
        "fullkit": "fullkit",
        "full": "fullkit",
        "fullkitcpu": "fullkit",
    }
    if k not in aliases:
        raise ValueError(f"unknown kit profile: {kit!r}")
    return aliases[k]


def want_cuda(kit: str, torch_flavor: str = "cuda") -> bool:
    """Return True if this kit must install a CUDA torch wheel."""
    profile = normalize_kit(kit)
    flavor = (torch_flavor or "cuda").strip().lower()
    if flavor not in ("cuda", "cpu"):
        raise ValueError(f"unknown TorchFlavor: {torch_flavor!r}")
    if profile in ("mini", "lite"):
        return flavor == "cuda"
    # fullkit
    return flavor == "cuda"


def index_url(kit: str, torch_flavor: str = "cuda") -> str:
    return PYTORCH_CU128_INDEX if want_cuda(kit, torch_flavor) else PYTORCH_CPU_INDEX


def is_torch_family_wheel(filename: str) -> bool:
    base = filename.replace("\\", "/").split("/")[-1]
    return bool(_TORCH_FAMILY.match(base))


def is_cuda_variant_wheel(filename: str) -> bool:
    base = filename.replace("\\", "/").split("/")[-1]
    return bool(_CUDA_MARK.search(base))


def is_cpu_variant_wheel(filename: str) -> bool:
    """CPU only if explicitly tagged +cpu.

    Unmarked PyPI torch wheels on Windows are ambiguous (often CUDA-capable)
    and must NOT be treated as CPU — require the +cpu local version tag.
    """
    base = filename.replace("\\", "/").split("/")[-1]
    if not is_torch_family_wheel(base):
        return False
    if is_cuda_variant_wheel(base):
        return False
    return bool(_CPU_MARK.search(base))


def wheel_matches_policy(filename: str, want_cuda_flag: bool) -> bool:
    if not is_torch_family_wheel(filename):
        return False
    if want_cuda_flag:
        return is_cuda_variant_wheel(filename)
    return is_cpu_variant_wheel(filename)


def filter_torch_wheels(
    filenames: Sequence[str], *, want_cuda_flag: bool
) -> tuple[List[str], List[str]]:
    """Split torch-family wheels into (selected, rejected) by policy."""
    selected: List[str] = []
    rejected: List[str] = []
    for name in filenames:
        if not is_torch_family_wheel(name):
            continue
        if wheel_matches_policy(name, want_cuda_flag):
            selected.append(name)
        else:
            rejected.append(name)
    return selected, rejected


def select_torch_wheels_or_refuse(
    filenames: Sequence[str], *, want_cuda_flag: bool
) -> List[str]:
    """Return matching torch-family wheels; empty list if none (caller may fall back to index).

    Never returns the opposite variant. If only the wrong variant exists, returns [].
    """
    selected, _rejected = filter_torch_wheels(filenames, want_cuda_flag=want_cuda_flag)
    return selected


def policy_dict(kit: str, torch_flavor: str = "cuda") -> dict:
    wc = want_cuda(kit, torch_flavor)
    return {
        "kit": normalize_kit(kit),
        "torch_flavor": (torch_flavor or "cuda").strip().lower(),
        "want_cuda": wc,
        "index_url": PYTORCH_CU128_INDEX if wc else PYTORCH_CPU_INDEX,
        "assert_cuda_is_none": not wc,
    }


def main(argv: Iterable[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Portable torch wheel policy")
    p.add_argument("--kit", required=True, help="mini|lite|fullkit")
    p.add_argument("--flavor", default="cuda", choices=("cuda", "cpu"))
    p.add_argument(
        "--list-wheels",
        default="",
        help="Comma-separated wheel filenames to filter (optional)",
    )
    p.add_argument("--json", action="store_true", help="Print policy as JSON")
    args = p.parse_args(list(argv) if argv is not None else None)

    pol = policy_dict(args.kit, args.flavor)
    names = [x.strip() for x in args.list_wheels.split(",") if x.strip()]
    if names:
        selected, rejected = filter_torch_wheels(names, want_cuda_flag=pol["want_cuda"])
        pol["selected"] = selected
        pol["rejected"] = rejected
        if not selected and any(is_torch_family_wheel(n) for n in names):
            pol["cache_mismatch"] = True
            pol["advice"] = (
                "CUDA-only cache with CPU kit (or vice versa): "
                "do not install opposite variant; use profile index_url or refuse."
            )
        else:
            pol["cache_mismatch"] = False

    if args.json:
        print(json.dumps(pol, indent=2))
    else:
        print(
            f"kit={pol['kit']} want_cuda={pol['want_cuda']} index={pol['index_url']}"
        )
        if names:
            print(f"selected={len(pol.get('selected', []))} rejected={len(pol.get('rejected', []))}")
    if names and pol.get("cache_mismatch"):
        if not args.json:
            print("CACHE_MISMATCH", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
