#!/usr/bin/env python3
"""Fetch and verify Depth Anything 3 (DA3) weights for MuraveiVision PRO.

URL and sha256 definitions are read strictly from scripts/portable_manifest.json (Z1 Zero-Hardcode).
Air-gap policy: This script is intended for the builder/staging machine, never auto-called in runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "scripts" / "portable_manifest.json"

# Seeded variants (nested/mono intentionally excluded — see mission report).
DA3_VARIANTS = ("base", "large", "metric", "giant")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()


def load_manifest_root() -> dict[str, Any]:
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"portable_manifest.json not found at {MANIFEST_PATH}")
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_da3_manifest() -> dict[str, Any]:
    """Load DA3 config from single-source node sidecars.da3 (N4 / Z1)."""
    data = load_manifest_root()
    da3_cfg = (data.get("sidecars") or {}).get("da3") or {}
    if not da3_cfg:
        raise ValueError("sidecars.da3 definition missing in scripts/portable_manifest.json")
    return da3_cfg


def _weight_filename(info: dict[str, Any], variant: str) -> str:
    return str(info.get("file") or info.get("filename") or f"da3_{variant}.safetensors")


def write_manifest_sha(variant: str, sha256: str) -> None:
    """Persist real sha256 into sidecars.da3.weights.<variant> (Z1)."""
    data = load_manifest_root()
    weights = ((data.get("sidecars") or {}).get("da3") or {}).get("weights") or {}
    if variant not in weights:
        raise KeyError(f"variant {variant} missing in sidecars.da3.weights")
    weights[variant]["sha256"] = sha256.lower()
    # Keep file/filename aliases in sync
    fn = _weight_filename(weights[variant], variant)
    weights[variant]["file"] = fn
    weights[variant]["filename"] = fn
    MANIFEST_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[MANIFEST] updated sidecars.da3.weights.{variant}.sha256")


def _download_with_curl(url: str, dest: Path) -> None:
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if not curl:
        raise RuntimeError("curl not found on PATH")
    cmd = [
        curl,
        "-L",
        "--fail",
        "--retry",
        "3",
        "--retry-delay",
        "5",
        "-o",
        str(dest),
        url,
    ]
    print(f"[download] curl → {dest.name}")
    subprocess.run(cmd, check=True)


def _download_with_urllib(url: str, dest: Path) -> None:
    print(f"[download] urllib → {dest.name}")
    urllib.request.urlretrieve(url, dest)


def download_file(url: str, dest: Path) -> None:
    """Prefer curl on Windows (urllib may stall on large HF files)."""
    try:
        _download_with_curl(url, dest)
    except Exception as curl_exc:
        print(f"[WARN] curl download failed ({curl_exc}); falling back to urllib", file=sys.stderr)
        if dest.exists():
            dest.unlink()
        _download_with_urllib(url, dest)


def fetch_weight(
    variant: str,
    cfg: dict[str, Any],
    target_dir: Path,
    verify_only: bool = False,
    update_manifest: bool = False,
) -> bool:
    weights_dict = cfg.get("weights", {})
    if variant not in weights_dict:
        print(f"[ERROR] Unknown DA3 variant: {variant}. Available: {list(weights_dict.keys())}", file=sys.stderr)
        return False

    info = weights_dict[variant]
    filename = _weight_filename(info, variant)
    url = info.get("url")
    expected_hash = (info.get("sha256") or "").strip().lower()
    is_placeholder_hash = not expected_hash or "fetch_real" in expected_hash

    if not url:
        print(f"[ERROR] URL missing for DA3 variant '{variant}' in manifest (Z1)", file=sys.stderr)
        return False

    dest = target_dir / filename
    if dest.is_file() and dest.stat().st_size > 0:
        got_hash = _sha256_file(dest)
        if not is_placeholder_hash and got_hash == expected_hash:
            print(f"[OK] {dest.name} present and verified SHA256: {got_hash}")
            return True
        if is_placeholder_hash:
            print(f"[WARN] {dest.name} present, sha256 is placeholder in manifest: {got_hash}")
            if update_manifest:
                write_manifest_sha(variant, got_hash)
            return True
        print(f"[WARN] {dest.name} SHA256 mismatch (got {got_hash}, expected {expected_hash})")
        if verify_only:
            return False
        # re-download below

    if verify_only:
        print(f"[FAIL] {dest.name} not found or hash mismatch in {target_dir}")
        return False

    target_dir.mkdir(parents=True, exist_ok=True)
    temp_dest = target_dir / f"{filename}.part"
    if temp_dest.exists():
        temp_dest.unlink()
    print(f"Downloading {variant} DA3 weights ({filename})...")
    print(f"From: {url}")
    print(f"To:   {dest}")

    try:
        download_file(str(url), temp_dest)
    except Exception as exc:
        if temp_dest.exists():
            temp_dest.unlink()
        print(f"[ERROR] Download failed: {exc}", file=sys.stderr)
        return False

    got_hash = _sha256_file(temp_dest)
    if not is_placeholder_hash and got_hash != expected_hash:
        temp_dest.unlink()
        print(f"[ERROR] SHA256 mismatch! Got: {got_hash}, Expected: {expected_hash}", file=sys.stderr)
        return False
    if is_placeholder_hash:
        print(f"[WARNING] Placeholder sha256 — real SHA256: {got_hash}")
        if update_manifest:
            write_manifest_sha(variant, got_hash)

    temp_dest.replace(dest)
    print(f"[SUCCESS] Staged {dest.name} (SHA256: {got_hash})")
    if update_manifest and not is_placeholder_hash:
        # ensure file aliases present
        write_manifest_sha(variant, got_hash)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch/verify DA3 model weights from manifest definitions.")
    parser.add_argument(
        "--variant",
        choices=[*DA3_VARIANTS, "all"],
        default="base",
        help="Model variant to fetch (default: base). 'all' = base+large+metric+giant",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help="Target output directory (defaults to manifest dest_relative: sidecars/da3)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify existing weight files without downloading",
    )
    parser.add_argument(
        "--update-manifest",
        action="store_true",
        help="Write real sha256 back into scripts/portable_manifest.json after download",
    )
    args = parser.parse_args()

    try:
        cfg = load_da3_manifest()
    except Exception as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 1

    dest_rel = cfg.get("dest_relative", "sidecars/da3")
    target_dir = Path(args.out_dir).resolve() if args.out_dir else (REPO_ROOT / dest_rel).resolve()

    variants = list(DA3_VARIANTS) if args.variant == "all" else [args.variant]
    success = True
    for v in variants:
        ok = fetch_weight(
            v,
            cfg,
            target_dir,
            verify_only=args.verify_only,
            update_manifest=args.update_manifest,
        )
        if not ok:
            success = False

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
