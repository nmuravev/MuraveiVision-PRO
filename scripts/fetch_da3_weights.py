#!/usr/bin/env python3
"""Fetch and verify Depth Anything 3 (DA3) weights for MuraveiVision PRO.

URL and sha256 definitions are read strictly from scripts/portable_manifest.json (Z1 Zero-Hardcode).
Air-gap policy: This script is intended for the builder/staging machine, never auto-called in runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "scripts" / "portable_manifest.json"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest().lower()


def load_da3_manifest() -> dict[str, Any]:
    """Load DA3 config from single-source node sidecars.da3 (N4 / Z1)."""
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"portable_manifest.json not found at {MANIFEST_PATH}")
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    da3_cfg = (data.get("sidecars") or {}).get("da3") or {}
    if not da3_cfg:
        raise ValueError("sidecars.da3 definition missing in scripts/portable_manifest.json")
    return da3_cfg


def fetch_weight(
    variant: str,
    cfg: dict[str, Any],
    target_dir: Path,
    verify_only: bool = False,
) -> bool:
    weights_dict = cfg.get("weights", {})
    if variant not in weights_dict:
        print(f"[ERROR] Unknown DA3 variant: {variant}. Available: {list(weights_dict.keys())}", file=sys.stderr)
        return False

    # TODO: verify URL on huggingface.co/depth-anything/ (verify DA3-BASE and DA3-LARGE URL & filename casing)
    # URLs in portable_manifest.json are flagged as VERIFIABLE / subject to operator confirmation
    info = weights_dict[variant]
    filename = info.get("filename") or f"da3_{variant}.safetensors"
    url = info.get("url")
    expected_hash = (info.get("sha256") or "").strip().lower()
    is_placeholder_hash = not expected_hash or "fetch_real" in expected_hash

    if not url:
        print(f"[ERROR] URL missing for DA3 variant '{variant}' in manifest (Z1)", file=sys.stderr)
        return False

    dest = target_dir / filename
    if dest.is_file():
        got_hash = _sha256_file(dest)
        if not is_placeholder_hash and got_hash == expected_hash:
            print(f"[OK] {dest.name} present and verified SHA256: {got_hash}")
            return True
        elif is_placeholder_hash:
            print(f"[WARN] {dest.name} present, sha256 is placeholder in manifest: {got_hash}")
            return True
        else:
            print(f"[WARN] {dest.name} SHA256 mismatch (got {got_hash}, expected {expected_hash})")
            if verify_only:
                return False

    if verify_only:
        print(f"[FAIL] {dest.name} not found in {target_dir}")
        return False

    target_dir.mkdir(parents=True, exist_ok=True)
    temp_dest = target_dir / f"{filename}.part"
    print(f"Downloading {variant} DA3 weights ({filename})...")
    print(f"From: {url} (VERIFIABLE: check huggingface.co/depth-anything/ if link changes)")
    print(f"To:   {dest}")

    try:
        urllib.request.urlretrieve(url, temp_dest)
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
    elif is_placeholder_hash:
        print(
            f"[WARNING] Downloaded with placeholder sha256 in manifest "
            f"(FETCH_REAL_SHA_AFTER_FIRST_DOWNLOAD). Real SHA256: {got_hash} — update sidecars.da3"
        )

    temp_dest.replace(dest)
    print(f"[SUCCESS] Staged {dest.name} (SHA256: {got_hash})")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch/verify DA3 model weights from manifest definitions.")
    parser.add_argument(
        "--variant",
        choices=["base", "large", "all"],
        default="base",
        help="Model variant to fetch (default: base)",
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
    args = parser.parse_args()

    try:
        cfg = load_da3_manifest()
    except Exception as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return 1

    dest_rel = cfg.get("dest_relative", "sidecars/da3")
    target_dir = Path(args.out_dir).resolve() if args.out_dir else (REPO_ROOT / dest_rel).resolve()

    variants = ["base", "large"] if args.variant == "all" else [args.variant]
    success = True
    for v in variants:
        ok = fetch_weight(v, cfg, target_dir, verify_only=args.verify_only)
        if not ok:
            success = False

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
