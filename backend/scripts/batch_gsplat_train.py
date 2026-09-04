"""Batch gsplat train for archive/recon jobs (reuse gsplat_train_job.py)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "backend"))
from services.job_ids import join_job_id_tokens  # noqa: E402
from services.recon_diagnose import get_best_sparse_dir  # noqa: E402

RECON_ROOT = BASE / "archive" / "recon"
PY = BASE / "muravei_env" / "Scripts" / "python.exe"
TRAIN_SCRIPT = BASE / "backend" / "scripts" / "gsplat_train_job.py"
BOOTSTRAP_SCRIPT = BASE / "backend" / "scripts" / "bootstrap_model_ply.py"


def _read_manifest(job_dir: Path) -> dict:
    path = job_dir / "manifest.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(job_dir: Path, data: dict) -> None:
    (job_dir / "manifest.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _patch_manifest(job_dir: Path) -> str | None:
    man = _read_manifest(job_dir)
    artifact: str | None = None
    if (job_dir / "model.ply").is_file():
        artifact = "model.ply"
        man["status"] = "done"
    elif (job_dir / "preview.ply").is_file():
        artifact = "preview.ply"
        if man.get("status") not in ("done", "error"):
            man["status"] = "colmap_done"
    meta_path = job_dir / "gsplat_meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            artifact = meta.get("artifact") or artifact
        except json.JSONDecodeError:
            pass
    if artifact:
        man["artifact"] = artifact
        _write_manifest(job_dir, man)
    return artifact


def _bootstrap_job(job_dir: Path, max_points: int) -> int:
    py = str(PY if PY.is_file() else Path(sys.executable))
    cmd = [py, str(BOOTSTRAP_SCRIPT), "--job-dir", str(job_dir), "--max-points", str(max_points)]
    print("running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(BASE))
    if proc.returncode != 0:
        return proc.returncode
    _patch_manifest(job_dir)
    return 0


def _train_job(job_dir: Path, max_steps: int, data_factor: int, force: bool, bootstrap_only: bool) -> int:
    if get_best_sparse_dir(job_dir) is None:
        print(f"skip {job_dir.name}: no valid colmap/sparse/N")
        return 0

    if bootstrap_only:
        return _bootstrap_job(job_dir, max_points=80_000)

    if (job_dir / "model.ply").is_file() and not force:
        print(f"skip {job_dir.name}: model.ply exists")
        _patch_manifest(job_dir)
        return 0

    py = str(PY if PY.is_file() else Path(sys.executable))
    cmd = [
        py,
        str(TRAIN_SCRIPT),
        "--job-dir",
        str(job_dir),
        "--max-steps",
        str(max_steps),
        "--data-factor",
        str(data_factor),
    ]
    print("running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(BASE))
    if proc.returncode != 0:
        print(f"train failed for {job_dir.name}, trying bootstrap model.ply", file=sys.stderr)
        code = _bootstrap_job(job_dir, max_points=80_000)
        if code == 0:
            print(f"OK {job_dir.name}: bootstrap model.ply")
            return 0
        print(f"FAIL {job_dir.name}: exit {proc.returncode}", file=sys.stderr)
        return proc.returncode

    artifact = _patch_manifest(job_dir)
    print(f"OK {job_dir.name}: artifact={artifact}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch gsplat train for recon jobs")
    ap.add_argument(
        "--job-id",
        nargs="+",
        metavar="HEX",
        help="Single job id under archive/recon/ (whitespace tokens are joined)",
    )
    ap.add_argument("--force", action="store_true", help="Retrain even if model.ply exists")
    ap.add_argument(
        "--max-steps",
        type=int,
        default=int(os.environ.get("GSPLAT_MAX_STEPS", "7000")),
    )
    ap.add_argument("--data-factor", type=int, default=4)
    ap.add_argument("--bootstrap-only", action="store_true", help="Skip train; export COLMAP→model.ply bootstrap")
    ap.add_argument("--recon-root", type=Path, default=RECON_ROOT)
    args = ap.parse_args()

    if not TRAIN_SCRIPT.is_file():
        print(f"missing {TRAIN_SCRIPT}", file=sys.stderr)
        return 1
    if not args.recon_root.is_dir():
        print(f"recon root missing: {args.recon_root}", file=sys.stderr)
        return 1

    job_dirs: list[Path] = []
    job_id = join_job_id_tokens(args.job_id)
    if job_id:
        job_dirs = [args.recon_root / job_id]
    else:
        for child in sorted(args.recon_root.iterdir()):
            if child.is_dir() and (child / "manifest.json").is_file():
                job_dirs.append(child)

    rc = 0
    for job_dir in job_dirs:
        if not job_dir.is_dir():
            print(f"missing job dir: {job_dir}", file=sys.stderr)
            rc = 1
            continue
        code = _train_job(job_dir, args.max_steps, args.data_factor, args.force, args.bootstrap_only)
        if code:
            rc = code
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
