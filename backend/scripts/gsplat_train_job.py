"""Minimal gsplat train for a recon job folder (COLMAP sparse + frames).

Expects layout:
  job_dir/frames/*.jpg
  job_dir/colmap/sparse/N/  (best model via get_best_sparse_dir; TXT or BIN)

Writes job_dir/model.ply and returns relative name on success.
Trainer staging still uses gsplat_data/sparse/0/ (gsplat examples layout).

  .\\muravei_env\\Scripts\\python.exe backend\\scripts\\gsplat_train_job.py --job-dir archive/recon/<id>

Requires: torch+cuda, gsplat (prebuilt wheel). Short iteration budget for field use.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "backend"))
from services.job_ids import sanitize_job_dir  # noqa: E402
from services.recon_diagnose import get_best_sparse_dir  # noqa: E402


def _fail(msg: str) -> int:
    print(f"gsplat_train: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-dir", required=True, type=Path)
    ap.add_argument("--max-steps", type=int, default=500)
    ap.add_argument("--data-factor", type=int, default=4)
    args = ap.parse_args()

    job_dir = args.job_dir
    if not job_dir.is_absolute():
        job_dir = (BASE / job_dir).resolve()
    job_dir = sanitize_job_dir(job_dir)
    if not job_dir.is_dir():
        return _fail(f"job dir missing: {job_dir}")

    frames = job_dir / "frames"
    sparse = get_best_sparse_dir(job_dir)
    if not frames.is_dir() or sparse is None:
        return _fail("need frames/ and valid colmap/sparse/N/")

    try:
        import torch
    except ImportError:
        return _fail("torch not installed")
    if not torch.cuda.is_available():
        return _fail("CUDA unavailable")

    try:
        import gsplat  # noqa: F401
    except ImportError:
        return _fail("gsplat not installed — pip install prebuilt wheel into muravei_env")

    # Preferred: vendor simple_trainer if present under sidecars/gsplat_examples
    trainer = BASE / "sidecars" / "gsplat_examples" / "simple_trainer.py"
    result_dir = job_dir / "gsplat_out"
    if result_dir.exists():
        shutil.rmtree(result_dir, ignore_errors=True)
    result_dir.mkdir(parents=True, exist_ok=True)

    # COLMAP dataset layout expected by gsplat examples: images/ + sparse/0/
    data_dir = job_dir / "gsplat_data"
    if data_dir.exists():
        shutil.rmtree(data_dir, ignore_errors=True)
    data_dir.mkdir(parents=True)
    images_link = data_dir / "images"
    sparse_link = data_dir / "sparse" / "0"
    sparse_link.mkdir(parents=True, exist_ok=True)
    # Copy/symlink frames → images (Windows: copy is safer)
    shutil.copytree(frames, images_link)
    for name in ("cameras.bin", "images.bin", "points3D.bin", "cameras.txt", "images.txt", "points3D.txt"):
        src = sparse / name
        if src.is_file():
            shutil.copy2(src, sparse_link / name)

    if trainer.is_file():
        import subprocess

        cmd = [
            sys.executable,
            str(trainer),
            "default",
            "--disable_viewer",
            "--disable_video",
            "--data_dir",
            str(data_dir),
            "--data_factor",
            str(args.data_factor),
            "--result_dir",
            str(result_dir),
            "--max_steps",
            str(args.max_steps),
            "--save_ply",
            "--ply_steps",
            str(args.max_steps),
            # Avoid mid-run traj crash on tiny camera sets; still eval at end.
            "--eval_steps",
            str(args.max_steps),
        ]
        print("running:", " ".join(cmd))
        proc = subprocess.run(cmd, cwd=str(trainer.parent))
        if proc.returncode != 0:
            return _fail(f"simple_trainer exit {proc.returncode}")
    else:
        # No vendored trainer — export a colored point PLY from COLMAP as interim artifact
        # (not true 3DGS; Flight3D still uses sparse_points.json). Document in stderr.
        print(
            "gsplat_train: sidecars/gsplat_examples/simple_trainer.py missing — "
            "exporting COLMAP points as preview.ply (not full 3DGS)",
            file=sys.stderr,
        )
        pts_txt = sparse / "points3D.txt"
        out_ply = job_dir / "preview.ply"
        if not pts_txt.is_file():
            return _fail("points3D.txt missing; convert COLMAP model to TXT first")
        _export_colmap_points_ply(pts_txt, out_ply)
        meta = {"artifact": "preview.ply", "kind": "colmap_points_ply", "gsplat": False}
        (job_dir / "gsplat_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print(out_ply.name)
        return 0

    # Locate exported ply
    ply_candidates = sorted(result_dir.rglob("*.ply"))
    if not ply_candidates:
        return _fail("no .ply produced")
    dest = job_dir / "model.ply"
    shutil.copy2(ply_candidates[-1], dest)
    meta = {"artifact": "model.ply", "kind": "gsplat", "gsplat": True, "steps": args.max_steps}
    (job_dir / "gsplat_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(dest.name)
    return 0


def _export_colmap_points_ply(points3d_txt: Path, out_ply: Path, max_points: int = 200_000) -> None:
    verts: list[tuple[float, float, float, int, int, int]] = []
    for line in points3d_txt.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
        r, g, b = int(float(parts[4])), int(float(parts[5])), int(float(parts[6]))
        verts.append((x, y, z, r, g, b))
        if len(verts) >= max_points:
            break
    with out_ply.open("w", encoding="ascii", newline="\n") as fh:
        fh.write("ply\nformat ascii 1.0\n")
        fh.write(f"element vertex {len(verts)}\n")
        fh.write("property float x\nproperty float y\nproperty float z\n")
        fh.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        fh.write("end_header\n")
        for x, y, z, r, g, b in verts:
            fh.write(f"{x} {y} {z} {r} {g} {b}\n")


if __name__ == "__main__":
    raise SystemExit(main())
