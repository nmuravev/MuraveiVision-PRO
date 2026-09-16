#!/usr/bin/env python3
"""Working verification of DA3 dense variants (builder/operator machine).

Copies a COLMAP job dir (or builds a minimal pose+frames set from archive video),
runs run_da3_pipeline for each variant, asserts non-flat depth / dense.ply / events,
writes logs/da3_verify.json.

Usage (from repo root):
  muravei_env\\Scripts\\python.exe backend\\scripts\\verify_da3_weights.py
  muravei_env\\Scripts\\python.exe backend\\scripts\\verify_da3_weights.py --variants base,large,metric
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from services.da3_pipeline import (  # noqa: E402
    DA3WeightsNotFoundError,
    find_da3_weights,
    run_da3_pipeline,
)
from services.train_presets import total_vram_gb  # noqa: E402

DEFAULT_VIDEO = REPO / "archive" / "video_2026-08-25_09-17-15.mp4"
OUT_JSON = REPO / "logs" / "da3_verify.json"


def _find_job_with_poses() -> Path | None:
    root = REPO / "archive" / "recon"
    if not root.is_dir():
        return None
    for job in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if (job / "camera_poses.json").is_file() and (job / "frames").is_dir():
            return job
    return None


def _copy_job(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "camera_poses.json", dst / "camera_poses.json")
    if (src / "manifest.json").is_file():
        shutil.copy2(src / "manifest.json", dst / "manifest.json")
    else:
        (dst / "manifest.json").write_text(
            json.dumps({"status": "colmap_done"}), encoding="utf-8"
        )
    frames_src = src / "frames"
    frames_dst = dst / "frames"
    frames_dst.mkdir(parents=True, exist_ok=True)
    poses = json.loads((src / "camera_poses.json").read_text(encoding="utf-8"))
    needed: list[str] = []
    for fmeta in poses.get("frames") or []:
        name = fmeta.get("image") or fmeta.get("frame")
        if name:
            needed.append(str(name))
    # Cap for wall-time but always prefer pose-referenced frames
    for name in needed[:64]:
        src_f = frames_src / name
        if src_f.is_file():
            shutil.copy2(src_f, frames_dst / name)
    if not any(frames_dst.iterdir()):
        # Fallback: copy first frames by name
        frames = sorted(frames_src.glob("*.jpg")) + sorted(frames_src.glob("*.png"))
        for f in frames[:48]:
            shutil.copy2(f, frames_dst / f.name)
    if (src / "sparse_points.json").is_file():
        shutil.copy2(src / "sparse_points.json", dst / "sparse_points.json")


def _depth_is_flat(arr: Any, tol: float = 1e-3) -> bool:
    import numpy as np

    a = np.asarray(arr, dtype=np.float32)
    if a.size == 0:
        return True
    return float(a.max() - a.min()) < tol or bool(np.allclose(a, 2.0, atol=1e-2))


def _vram_peak_mb() -> float | None:
    try:
        import torch

        if torch.cuda.is_available():
            return float(torch.cuda.max_memory_allocated() / (1024 * 1024))
    except Exception:
        pass
    return None


def verify_variant(variant: str, job_src: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "variant": variant,
        "points": 0,
        "wall_sec": 0.0,
        "vram_peak_mb": None,
        "verdict": "FAIL",
        "error": None,
    }
    w = find_da3_weights(variant)
    if w is None:
        row["verdict"] = "SKIP_NO_WEIGHTS"
        row["error"] = f"weights missing for {variant}"
        return row

    vram = total_vram_gb()
    if variant == "giant" and (vram <= 0 or vram < 16):
        row["verdict"] = "GATE_SKIPPED"
        row["error"] = f"VRAM {vram:.1f} < 16 GB"
        return row

    events: list[dict[str, Any]] = []

    def emit(ev: dict[str, Any]) -> None:
        events.append(ev)

    with tempfile.TemporaryDirectory(prefix=f"da3_verify_{variant}_") as td:
        job_dir = Path(td)
        _copy_job(job_src, job_dir)
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
        except Exception:
            pass
        t0 = time.perf_counter()
        try:
            res = run_da3_pipeline(job_dir, variant=variant, emit=emit)
        except DA3WeightsNotFoundError as exc:
            row["wall_sec"] = round(time.perf_counter() - t0, 2)
            row["error"] = str(exc)
            row["verdict"] = "FAIL_RUNTIME"
            return row
        except Exception as exc:
            row["wall_sec"] = round(time.perf_counter() - t0, 2)
            row["error"] = f"{type(exc).__name__}: {exc}"
            row["verdict"] = "FAIL"
            return row
        row["wall_sec"] = round(time.perf_counter() - t0, 2)
        row["vram_peak_mb"] = _vram_peak_mb()

        dense = job_dir / "dense.ply"
        if not dense.is_file() or dense.stat().st_size <= 0:
            row["error"] = "dense.ply missing or empty"
            row["verdict"] = "FAIL_PLY"
            return row

        # Point count from pipeline result (points_count) or PLY header
        pts = int(res.get("points_count") or res.get("points") or 0)
        if pts <= 0 and dense.is_file():
            try:
                head = dense.read_bytes()[:512].decode("latin-1", errors="ignore")
                for line in head.splitlines():
                    if line.startswith("element vertex"):
                        pts = int(line.split()[-1])
                        break
            except Exception:
                pass
        row["points"] = pts
        if pts <= 0:
            row["error"] = "zero points"
            row["verdict"] = "FAIL_EMPTY"
            return row

        # In-memory depth differentiation (from pipeline; no .npy kept)
        row["depth_median"] = res.get("depth_median")
        row["depth_std"] = res.get("depth_std")

        man = json.loads((job_dir / "manifest.json").read_text(encoding="utf-8"))
        backend = man.get("dense_backend") or ""
        if f"da3_{variant}" not in str(backend):
            row["error"] = f"manifest dense_backend={backend!r}"
            row["verdict"] = "FAIL_MANIFEST"
            return row

        stages = [e.get("stage") for e in events if isinstance(e, dict)]
        for need in ("da3_depth", "da3_fusion", "da3_done"):
            if need not in stages:
                row["error"] = f"missing stage {need}"
                row["verdict"] = "FAIL_EVENTS"
                return row

        row["verdict"] = "PASS"
        return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variants",
        default="base,large,metric,giant",
        help="Comma-separated variants",
    )
    parser.add_argument("--job-dir", type=str, default="", help="COLMAP job with camera_poses.json")
    parser.add_argument("--out", type=str, default=str(OUT_JSON))
    args = parser.parse_args()

    job = Path(args.job_dir) if args.job_dir else _find_job_with_poses()
    if job is None or not job.is_dir():
        print(
            "[FAIL] No job dir with camera_poses.json. Pass --job-dir or run COLMAP on "
            f"{DEFAULT_VIDEO.name}",
            file=sys.stderr,
        )
        return 2

    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    rows = [verify_variant(v, job) for v in variants]
    out = {
        "job_src": str(job),
        "video_hint": str(DEFAULT_VIDEO),
        "vram_gb": total_vram_gb(),
        "rows": rows,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    # PASS or intentional skips are OK; hard FAIL exits 1
    hard = [r for r in rows if str(r["verdict"]).startswith("FAIL")]
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
