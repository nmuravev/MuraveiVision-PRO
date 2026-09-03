"""Bootstrap model.ply from COLMAP points when full gsplat train is unavailable.

Writes a minimal 3D Gaussian PLY (not photorealistic) so Flight3D «Сцена» can load
DropInViewer and manifest.artifact can point to model.ply.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
C0 = 0.28209479177387814


def _parse_points3d_txt(path: Path, max_points: int) -> tuple[list, list]:
    verts: list[tuple[float, float, float]] = []
    colors: list[tuple[int, int, int]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
        r, g, b = int(float(parts[4])), int(float(parts[5])), int(float(parts[6]))
        verts.append((x, y, z))
        colors.append((r, g, b))
        if len(verts) >= max_points:
            break
    return verts, colors


def bootstrap_ply(job_dir: Path, max_points: int = 80_000) -> Path:
    sparse = job_dir / "colmap" / "sparse" / "0"
    pts_txt = sparse / "points3D.txt"
    if not pts_txt.is_file():
        raise FileNotFoundError(f"missing {pts_txt}")

    import torch
    from gsplat import export_splats

    verts, colors = _parse_points3d_txt(pts_txt, max_points)
    if not verts:
        raise ValueError("no COLMAP points parsed")

    means = torch.tensor(verts, dtype=torch.float32)
    n = means.shape[0]
    scales = torch.full((n, 3), 0.02, dtype=torch.float32)
    quats = torch.zeros((n, 4), dtype=torch.float32)
    quats[:, 0] = 1.0
    opacities = torch.full((n,), 0.85, dtype=torch.float32)
    rgb = torch.tensor(colors, dtype=torch.float32) / 255.0
    sh0 = (rgb - 0.5) / C0
    sh0 = sh0.unsqueeze(1)  # (N, 1, 3)
    shN = torch.zeros((n, 0, 3), dtype=torch.float32)

    out = job_dir / "model.ply"
    export_splats(
        means,
        scales,
        quats,
        opacities,
        sh0,
        shN,
        format="ply",
        save_to=str(out),
    )
    meta = {
        "artifact": "model.ply",
        "kind": "bootstrap_colmap",
        "gsplat": True,
        "note": "COLMAP points exported as Gaussians — run full gsplat train for photorealism",
    }
    (job_dir / "gsplat_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-dir", required=True, type=Path)
    ap.add_argument("--max-points", type=int, default=80_000)
    args = ap.parse_args()

    job_dir = args.job_dir
    if not job_dir.is_absolute():
        job_dir = (BASE / job_dir).resolve()
    points3d = job_dir / "colmap" / "sparse" / "0" / "points3D.txt"
    if not points3d.is_file():
        print(f"bootstrap_model_ply: missing {points3d}", file=sys.stderr)
        return 1
    try:
        out = bootstrap_ply(job_dir, max_points=args.max_points)
        print(out.name)
        return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"bootstrap_model_ply: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"bootstrap_model_ply: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
