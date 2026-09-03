"""CLI: diagnose archive/recon scenes (COLMAP + gsplat readiness)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "backend"))

from services.recon_diagnose import (  # noqa: E402
    exit_code_for,
    scan_recon_root,
)


def _print_table(diagnoses: list) -> None:
    header = (
        "job_id",
        "status",
        "artifact",
        "frames",
        "sparse",
        "model.ply",
        "preview",
        "train?",
        "trainer",
        "cuda",
        "gsplat",
    )
    print("\t".join(header))
    for d in diagnoses:
        print(
            "\t".join(
                [
                    d.job_id,
                    d.manifest_status or "-",
                    d.manifest_artifact or "-",
                    str(d.frames_count),
                    "Y" if d.colmap_sparse else "N",
                    "Y" if d.model_ply else "N",
                    "Y" if d.preview_ply else "N",
                    "Y" if d.needs_train else "N",
                    "Y" if d.trainer_ready else "N",
                    "Y" if d.cuda_available else "N",
                    "Y" if d.gsplat_installed else "N",
                ]
            )
        )
        if d.issues:
            print(f"  issues: {', '.join(d.issues)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnose archive/recon job folders")
    ap.add_argument("--json", action="store_true", help="JSON output")
    ap.add_argument("--job-id", help="Single job id under archive/recon/")
    ap.add_argument(
        "--recon-root",
        type=Path,
        default=BASE / "archive" / "recon",
        help="Recon root (default: archive/recon)",
    )
    args = ap.parse_args()

    diagnoses = scan_recon_root(args.recon_root, job_id=args.job_id)
    if args.json:
        print(json.dumps([d.to_dict() for d in diagnoses], indent=2, ensure_ascii=False))
    else:
        if not args.recon_root.is_dir():
            print(f"recon root missing: {args.recon_root}", file=sys.stderr)
        elif not diagnoses:
            print("no recon jobs found", file=sys.stderr)
        else:
            _print_table(diagnoses)

    return exit_code_for(diagnoses, args.recon_root)


if __name__ == "__main__":
    raise SystemExit(main())
