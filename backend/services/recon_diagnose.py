"""Diagnose archive/recon job folders (COLMAP + gsplat readiness)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parents[2]
RECON_ROOT = BASE_DIR / "archive" / "recon"
TRAINER_PATH = BASE_DIR / "sidecars" / "gsplat_examples" / "simple_trainer.py"


@dataclass
class JobDiagnosis:
    job_id: str
    job_dir: str
    ok: bool = False
    needs_train: bool = False
    colmap_sparse: bool = False
    frames_count: int = 0
    camera_poses: bool = False
    sparse_json: bool = False
    manifest_status: str | None = None
    manifest_artifact: str | None = None
    model_ply: bool = False
    preview_ply: bool = False
    gsplat_meta: bool = False
    trainer_ready: bool = False
    cuda_available: bool = False
    gsplat_installed: bool = False
    video_path: str | None = None
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_best_sparse_dir(job_dir: Path) -> Path | None:
    """Pick best COLMAP sparse/N (max points file size; cameras preferred).

    Multi-model mapper output may put a tiny/broken model in sparse/0 and the
    usable reconstruction in sparse/1, sparse/2, …
    """
    sparse_root = job_dir / "colmap" / "sparse"
    if not sparse_root.is_dir():
        return None

    best: Path | None = None
    best_score = -1
    for sparse_dir in sparse_root.iterdir():
        if not sparse_dir.is_dir():
            continue
        pts = sparse_dir / "points3D.bin"
        if not pts.is_file():
            pts = sparse_dir / "points3D.txt"
        if not pts.is_file():
            continue
        try:
            size = pts.stat().st_size
        except OSError:
            continue
        has_cam = (sparse_dir / "cameras.bin").is_file() or (sparse_dir / "cameras.txt").is_file()
        score = size + (1_000_000_000 if has_cam else 0)
        if score > best_score:
            best_score = score
            best = sparse_dir
    return best


def _sparse_ok(job_dir: Path) -> bool:
    return get_best_sparse_dir(job_dir) is not None


def _env_checks() -> tuple[bool, bool]:
    cuda = False
    gsplat = False
    try:
        import torch  # noqa: PLC0415

        cuda = bool(torch.cuda.is_available())
    except ImportError:
        pass
    try:
        import gsplat  # noqa: F401, PLC0415

        gsplat = True
    except ImportError:
        pass
    return cuda, gsplat


def diagnose_job(job_dir: Path, cuda: bool | None = None, gsplat: bool | None = None) -> JobDiagnosis:
    job_id = job_dir.name
    diag = JobDiagnosis(job_id=job_id, job_dir=str(job_dir))

    if cuda is None or gsplat is None:
        env_cuda, env_gsplat = _env_checks()
        cuda = env_cuda if cuda is None else cuda
        gsplat = env_gsplat if gsplat is None else gsplat
    diag.cuda_available = cuda
    diag.gsplat_installed = gsplat
    diag.trainer_ready = TRAINER_PATH.is_file()

    if not job_dir.is_dir():
        diag.issues.append("job_dir_missing")
        return diag

    frames_dir = job_dir / "frames"
    diag.frames_count = len(list(frames_dir.glob("*.jpg"))) if frames_dir.is_dir() else 0
    diag.colmap_sparse = _sparse_ok(job_dir)
    diag.camera_poses = (job_dir / "camera_poses.json").is_file()
    diag.sparse_json = (job_dir / "sparse_points.json").is_file()
    diag.model_ply = (job_dir / "model.ply").is_file()
    diag.preview_ply = (job_dir / "preview.ply").is_file()
    diag.gsplat_meta = (job_dir / "gsplat_meta.json").is_file()

    manifest_path = job_dir / "manifest.json"
    if manifest_path.is_file():
        try:
            man = json.loads(manifest_path.read_text(encoding="utf-8"))
            diag.manifest_status = man.get("status")
            diag.manifest_artifact = man.get("artifact")
            diag.video_path = man.get("video_path")
        except json.JSONDecodeError:
            diag.issues.append("manifest_invalid_json")

    if not diag.colmap_sparse:
        diag.issues.append("missing_colmap_sparse")
    if diag.frames_count == 0:
        diag.issues.append("missing_frames")
    if not diag.cuda_available:
        diag.issues.append("cuda_unavailable")
    if not diag.gsplat_installed:
        diag.issues.append("gsplat_not_installed")
    if not diag.trainer_ready:
        diag.issues.append("trainer_missing")

    has_splat = diag.model_ply or (diag.manifest_artifact or "").lower() == "model.ply"
    if diag.colmap_sparse and not has_splat:
        diag.needs_train = True
        if diag.trainer_ready and diag.cuda_available and diag.gsplat_installed:
            diag.issues.append("needs_gsplat_train")
        elif not has_splat:
            diag.issues.append("missing_model_ply")

    if diag.manifest_artifact and not diag.model_ply and not diag.preview_ply:
        diag.issues.append("manifest_artifact_file_missing")

    diag.ok = (
        diag.colmap_sparse
        and diag.frames_count > 0
        and has_splat
        and not any(
            i in diag.issues
            for i in ("manifest_artifact_file_missing", "job_dir_missing", "manifest_invalid_json")
        )
    )
    return diag


def scan_recon_root(
    recon_root: Path | None = None,
    job_id: str | None = None,
) -> list[JobDiagnosis]:
    root = recon_root or RECON_ROOT
    if not root.is_dir():
        return []

    cuda, gsplat = _env_checks()
    if job_id:
        return [diagnose_job(root / job_id, cuda=cuda, gsplat=gsplat)]

    jobs: list[JobDiagnosis] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "manifest.json").is_file():
            jobs.append(diagnose_job(child, cuda=cuda, gsplat=gsplat))
    return jobs


def exit_code_for(diagnoses: list[JobDiagnosis], recon_root: Path | None = None) -> int:
    root = recon_root or RECON_ROOT
    if not root.is_dir():
        return 1
    if not diagnoses:
        return 1
    if any(d.needs_train for d in diagnoses):
        return 2
    return 0
