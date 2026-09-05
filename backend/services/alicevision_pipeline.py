"""AliceVision dense MVS / textured mesh after COLMAP sparse.

Never fails the parent COLMAP job: on any AliceVision error, leave sparse
artifacts intact and surface a warning / partial ``manifest.artifacts``.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from services.alicevision import (
    alicevision_available,
    alicevision_bin,
    alicevision_cuda_ready,
    alicevision_env,
    alicevision_version,
    log_first_use,
)
from services.colmap_poses import _parse_cameras_txt, _parse_images_txt
from services.runtime_log import write as runtime_write

EmitFn = Callable[[dict[str, Any]], None]


def normalize_artifacts(man: dict[str, Any]) -> dict[str, Any]:
    """Back-compat: ensure ``artifacts`` / ``selected_artifact`` exist."""
    arts = man.get("artifacts")
    if not isinstance(arts, dict):
        arts = {}
    sparse_file = man.get("sparse_file") or "sparse_points.json"
    if "sparse" not in arts and sparse_file:
        arts["sparse"] = {"file": sparse_file}
    artifact = man.get("artifact")
    if artifact and isinstance(artifact, str):
        low = artifact.lower()
        if low.endswith(".obj") and "mesh" not in arts:
            arts["mesh"] = {"file": artifact}
        elif low in ("model.ply",) or low.endswith(".splat") or low.endswith(".ksplat"):
            if "splat" not in arts:
                arts["splat"] = {"file": artifact}
        elif low.endswith(".ply") and artifact not in (
            arts.get("dense", {}).get("file"),
            arts.get("sparse", {}).get("file"),
        ):
            # preview.ply / unknown ply → treat as sparse-ish points unless dense set
            if artifact == "dense_point_cloud.ply":
                arts.setdefault("dense", {"file": artifact})
            elif "splat" not in arts and artifact == "model.ply":
                arts["splat"] = {"file": artifact}
    man["artifacts"] = arts
    if not man.get("selected_artifact"):
        for key in ("mesh", "dense", "splat", "sparse"):
            entry = arts.get(key)
            if isinstance(entry, dict) and entry.get("file"):
                man["selected_artifact"] = key
                break
    return man


def _log(msg: str) -> None:
    runtime_write("info", "alicevision", msg)


def _warn(msg: str) -> None:
    runtime_write("warn", "alicevision", msg)


def _run_cli(
    tool: str,
    args: list[str],
    *,
    cwd: Path,
    timeout: int,
    emit: EmitFn | None,
    step: str,
) -> None:
    exe = alicevision_bin(tool)
    cmd = [str(exe), *args]
    env = {**os.environ, **alicevision_env()}
    _log(f"step={step} cmd={' '.join(cmd)}")
    if emit:
        emit(
            {
                "phase": f"alicevision_{step}",
                "stage": f"alicevision_{step}",
                "message": f"AliceVision · {step}…",
                "event": "alicevision-step-start",
                "alicevision_step": step,
            }
        )
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"AliceVision {step} timeout after {timeout}s") from exc
    except OSError as exc:
        raise RuntimeError(f"AliceVision {step} failed to start: {exc}") from exc

    if proc.returncode != 0:
        tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-800:]
        raise RuntimeError(f"AliceVision {step} exit {proc.returncode}: {tail}")
    if emit:
        emit(
            {
                "event": "alicevision-step-done",
                "alicevision_step": step,
                "message": f"AliceVision · {step} OK",
            }
        )


def _copy_frames(frames_dir: Path, dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in sorted(frames_dir.iterdir()):
        if not src.is_file():
            continue
        if src.suffix.lower() not in (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".exr"):
            continue
        shutil.copy2(src, dest / src.name)
        n += 1
    return n


def _rot_to_list(R: list[list[float]]) -> list[str]:
    # AliceVision pose rotation is row-major 3x3 as flat list of strings
    out: list[str] = []
    for row in R:
        for v in row:
            out.append(str(float(v)))
    return out


def _invert_w2c(R: list[list[float]], t: list[float]) -> tuple[list[list[float]], list[float]]:
    """COLMAP world-to-camera → AliceVision camera-to-world (R_c2w, center)."""
    # R_c2w = R_w2c^T ; C = -R_c2w @ t
    Rt = [
        [R[0][0], R[1][0], R[2][0]],
        [R[0][1], R[1][1], R[2][1]],
        [R[0][2], R[1][2], R[2][2]],
    ]
    cx = -(Rt[0][0] * t[0] + Rt[0][1] * t[1] + Rt[0][2] * t[2])
    cy = -(Rt[1][0] * t[0] + Rt[1][1] * t[1] + Rt[1][2] * t[2])
    cz = -(Rt[2][0] * t[0] + Rt[2][1] * t[1] + Rt[2][2] * t[2])
    return Rt, [cx, cy, cz]


def inject_colmap_poses(
    camera_init_sfm: Path,
    sparse_dir: Path,
    image_folder: Path,
    out_sfm: Path,
) -> int:
    """Merge COLMAP poses/intrinsics into cameraInit.sfm (match by basename)."""
    cams = _parse_cameras_txt(sparse_dir / "cameras.txt")
    images = _parse_images_txt(sparse_dir / "images.txt")
    by_name = {Path(im["image"]).name.lower(): im for im in images}

    sfm = json.loads(camera_init_sfm.read_text(encoding="utf-8"))
    views = sfm.get("views") or []
    if not views:
        raise RuntimeError("cameraInit.sfm has no views")

    # Build one AliceVision intrinsic per COLMAP camera
    av_intrinsics: list[dict[str, Any]] = []
    cam_id_to_intrinsic: dict[int, str] = {}
    for cam_id, cam in cams.items():
        w = int(cam["image_size"]["width"])
        h = int(cam["image_size"]["height"])
        fx = float(cam["intrinsics"]["fx"])
        fy = float(cam["intrinsics"]["fy"])
        cx = float(cam["intrinsics"]["cx"])
        cy = float(cam["intrinsics"]["cy"])
        sensor_w = 36.0
        sensor_h = sensor_w * (h / max(w, 1))
        focal_mm = (fx + fy) * 0.5 * sensor_w / max(w, 1)
        iid = str(1000 + int(cam_id))
        cam_id_to_intrinsic[cam_id] = iid
        av_intrinsics.append(
            {
                "intrinsicId": iid,
                "width": str(w),
                "height": str(h),
                "sensorWidth": str(sensor_w),
                "sensorHeight": str(sensor_h),
                "serialNumber": "-1",
                "type": "pinhole",
                "initializationMode": "calibrated",
                "initialFocalLength": "-1",
                "focalLength": str(focal_mm),
                "pixelRatio": str(fx / max(fy, 1e-9)),
                "pixelRatioLocked": "true",
                "offsetLocked": "false",
                "scaleLocked": "false",
                "principalPoint": [
                    str(cx - w / 2.0),
                    str(cy - h / 2.0),
                ],
                "distortionLocked": "false",
                "distortionInitializationMode": "none",
                "distortionParams": ["0", "0", "0"],
                "undistortionOffset": ["0", "0"],
                "undistortionParams": "",
                "distortionType": "none",
                "locked": "true",
            }
        )

    poses: list[dict[str, Any]] = []
    matched = 0
    for view in views:
        basename = Path(str(view.get("path") or "")).name.lower()
        col = by_name.get(basename)
        if not col:
            continue
        R_c2w, center = _invert_w2c(col["R"], col["t"])
        pose_id = str(view.get("poseId") or view.get("viewId"))
        view["poseId"] = pose_id
        view["intrinsicId"] = cam_id_to_intrinsic.get(int(col["camera_id"]), view.get("intrinsicId"))
        # Prefer absolute path under image_folder
        view["path"] = str((image_folder / Path(str(view.get("path") or "")).name).resolve())
        poses.append(
            {
                "poseId": pose_id,
                "pose": {
                    "transform": {
                        "rotation": _rot_to_list(R_c2w),
                        "center": [str(center[0]), str(center[1]), str(center[2])],
                    },
                    "locked": "1",
                },
            }
        )
        matched += 1

    if matched < 2:
        raise RuntimeError(f"COLMAP→SfM matched only {matched} views (need ≥2)")

    sfm["intrinsics"] = av_intrinsics
    sfm["poses"] = poses
    # Drop views without poses
    posed_ids = {p["poseId"] for p in poses}
    sfm["views"] = [v for v in views if str(v.get("poseId")) in posed_ids]
    out_sfm.write_text(json.dumps(sfm, indent=4), encoding="utf-8")
    return matched


def _file_size_mb(path: Path) -> float:
    try:
        return round(path.stat().st_size / (1024 * 1024), 3)
    except OSError:
        return 0.0


def run_dense_pipeline(
    job_dir: Path,
    *,
    mode: str = "dense",
    emit: EmitFn | None = None,
    frames_dir: Path | None = None,
    sparse_dir: Path | None = None,
) -> dict[str, Any]:
    """Run AliceVision dense (and optional mesh/texturing).

    ``mode``: ``dense`` (through meshing + dense PLY) or ``mesh`` (+ filter + texture).
    Returns result dict with ``ok``, ``artifacts``, ``warning`` / ``error``.
    """
    job_dir = Path(job_dir)
    frames_dir = Path(frames_dir or (job_dir / "frames"))
    sparse_dir = Path(sparse_dir or (job_dir / "colmap" / "sparse" / "0"))
    work = job_dir / "alicevision"
    av_input = job_dir / "alicevision_input"
    result: dict[str, Any] = {"ok": False, "artifacts": {}, "warning": None, "error": None}

    def _emit(ev: dict[str, Any]) -> None:
        if emit:
            emit(ev)

    if not alicevision_available():
        msg = "AliceVision не установлен (sidecar / ALICEVISION_ROOT)"
        result["error"] = msg
        result["warning"] = msg
        _emit({"event": "alicevision-discover", "available": False, "message": msg})
        return result

    cuda_ok, cuda_reason = alicevision_cuda_ready()
    if not cuda_ok:
        result["error"] = cuda_reason
        result["warning"] = cuda_reason
        _emit({"event": "alicevision-discover", "available": True, "cuda": False, "message": cuda_reason})
        return result

    log_first_use()
    ver = alicevision_version() or "unknown"
    _emit(
        {
            "event": "alicevision-discover",
            "available": True,
            "cuda": True,
            "version": ver,
            "message": f"AliceVision v{ver}",
        }
    )

    if not frames_dir.is_dir():
        result["error"] = f"frames missing: {frames_dir}"
        return result
    if not (sparse_dir / "images.txt").is_file() or not (sparse_dir / "cameras.txt").is_file():
        result["error"] = f"COLMAP text model missing in {sparse_dir}"
        return result

    try:
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)
        if av_input.exists():
            shutil.rmtree(av_input, ignore_errors=True)
        n_frames = _copy_frames(frames_dir, av_input)
        if n_frames < 2:
            raise RuntimeError(f"Need ≥2 frames in {frames_dir}, got {n_frames}")

        camera_init = work / "cameraInit.sfm"
        _run_cli(
            "cameraInit",
            [
                "--imageFolder",
                str(av_input.resolve()),
                "--output",
                str(camera_init),
                "--defaultFieldOfView",
                "45",
                "--allowSingleView",
                "1",
                "--verboseLevel",
                "info",
            ],
            cwd=work,
            timeout=600,
            emit=emit,
            step="cameraInit",
        )

        sfm = work / "sfm_colmap.sfm"
        matched = inject_colmap_poses(camera_init, sparse_dir, av_input, sfm)
        _log(f"injected COLMAP poses views={matched}")

        dense_dir = work / "dense"
        dense_dir.mkdir(parents=True, exist_ok=True)
        _run_cli(
            "prepareDenseScene",
            [
                "--input",
                str(sfm),
                "--output",
                str(dense_dir),
                "--outputFileType",
                "exr",
                "--verboseLevel",
                "info",
            ],
            cwd=work,
            timeout=3600,
            emit=emit,
            step="prepareDenseScene",
        )

        depth_dir = work / "depthMap"
        depth_dir.mkdir(parents=True, exist_ok=True)
        _run_cli(
            "depthMapEstimation",
            [
                "--input",
                str(sfm),
                "--imagesFolder",
                str(dense_dir),
                "--output",
                str(depth_dir),
                "--downscale",
                "2",
                "--verboseLevel",
                "info",
            ],
            cwd=work,
            timeout=int(os.environ.get("ALICEVISION_DEPTH_TIMEOUT", "14400")),
            emit=emit,
            step="depthMapEstimation",
        )

        depth_filt = work / "depthMapFiltered"
        depth_filt.mkdir(parents=True, exist_ok=True)
        _run_cli(
            "depthMapFiltering",
            [
                "--input",
                str(sfm),
                "--depthMapsFolder",
                str(depth_dir),
                "--output",
                str(depth_filt),
                "--verboseLevel",
                "info",
            ],
            cwd=work,
            timeout=7200,
            emit=emit,
            step="depthMapFiltering",
        )

        mesh_raw = work / "mesh.obj"
        dense_sfm = work / "dense.sfm"
        _run_cli(
            "meshing",
            [
                "--input",
                str(sfm),
                "--depthMapsFolder",
                str(depth_filt),
                "--output",
                str(dense_sfm),
                "--outputMesh",
                str(mesh_raw),
                "--verboseLevel",
                "info",
            ],
            cwd=work,
            timeout=7200,
            emit=emit,
            step="meshing",
        )

        dense_ply = job_dir / "dense_point_cloud.ply"
        # Prefer exportMeshlab PLY; fall back to convertMesh vertices
        try:
            _run_cli(
                "exportMeshlab",
                [
                    "--input",
                    str(dense_sfm if dense_sfm.is_file() else sfm),
                    "--ply",
                    str(dense_ply),
                    "--output",
                    str(work / "meshlab"),
                    "--verboseLevel",
                    "info",
                ],
                cwd=work,
                timeout=1800,
                emit=emit,
                step="exportMeshlab",
            )
        except RuntimeError as exc:
            _warn(f"exportMeshlab failed ({exc}); convertMesh fallback")
            if mesh_raw.is_file():
                _run_cli(
                    "convertMesh",
                    ["--inputMesh", str(mesh_raw), "--output", str(dense_ply)],
                    cwd=work,
                    timeout=600,
                    emit=emit,
                    step="convertMesh",
                )

        if dense_ply.is_file():
            result["artifacts"]["dense"] = {
                "file": dense_ply.name,
                "size_mb": _file_size_mb(dense_ply),
            }
            _emit({"event": "dense-artifact-ready", "file": dense_ply.name})

        mesh_out = job_dir / "textured_mesh.obj"
        if mode == "mesh":
            mesh_filt = work / "meshFiltered.obj"
            _run_cli(
                "meshFiltering",
                [
                    "--inputMesh",
                    str(mesh_raw),
                    "--outputMesh",
                    str(mesh_filt),
                    "--keepLargestMeshOnly",
                    "1",
                    "--verboseLevel",
                    "info",
                ],
                cwd=work,
                timeout=1800,
                emit=emit,
                step="meshFiltering",
            )
            tex_dir = work / "texturing"
            tex_dir.mkdir(parents=True, exist_ok=True)
            _run_cli(
                "texturing",
                [
                    "--input",
                    str(dense_sfm if dense_sfm.is_file() else sfm),
                    "--inputMesh",
                    str(mesh_filt if mesh_filt.is_file() else mesh_raw),
                    "--imagesFolder",
                    str(dense_dir),
                    "--output",
                    str(tex_dir),
                    "--outputMeshFileType",
                    "obj",
                    "--textureSide",
                    "4096",
                    "--downscale",
                    "2",
                    "--verboseLevel",
                    "info",
                ],
                cwd=work,
                timeout=7200,
                emit=emit,
                step="texturing",
            )
            # Meshroom writes texturedMesh.obj inside output folder
            candidates = list(tex_dir.glob("*.obj")) + list(tex_dir.glob("texturedMesh.*"))
            src_obj = None
            for c in tex_dir.rglob("*.obj"):
                src_obj = c
                break
            if src_obj and src_obj.is_file():
                # Copy obj + sidecar mtl/textures next to job root as textured_mesh.*
                shutil.copy2(src_obj, mesh_out)
                mtl = src_obj.with_suffix(".mtl")
                if mtl.is_file():
                    shutil.copy2(mtl, job_dir / "textured_mesh.mtl")
                for tex in src_obj.parent.glob("*.png"):
                    shutil.copy2(tex, job_dir / tex.name)
                for tex in src_obj.parent.glob("*.jpg"):
                    shutil.copy2(tex, job_dir / tex.name)
                result["artifacts"]["mesh"] = {
                    "file": mesh_out.name,
                    "size_mb": _file_size_mb(mesh_out),
                }
                _emit({"event": "mesh-artifact-ready", "file": mesh_out.name})
            elif mesh_filt.is_file():
                shutil.copy2(mesh_filt, mesh_out)
                result["artifacts"]["mesh"] = {
                    "file": mesh_out.name,
                    "size_mb": _file_size_mb(mesh_out),
                }
                _emit({"event": "mesh-artifact-ready", "file": mesh_out.name})

        result["ok"] = bool(result["artifacts"])
        if not result["ok"]:
            result["error"] = "AliceVision finished without dense/mesh artifacts"
            result["warning"] = result["error"]
        return result
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        _warn(msg)
        result["error"] = msg
        result["warning"] = msg
        _emit({"event": "alicevision-step-error", "message": msg, "error": msg})
        return result


def patch_manifest_artifacts(
    man: dict[str, Any],
    job_dir: Path,
    pipeline_result: dict[str, Any],
) -> dict[str, Any]:
    """Merge pipeline artifacts into manifest; preserve sparse/splat."""
    man = normalize_artifacts(man)
    arts = dict(man.get("artifacts") or {})
    for key, meta in (pipeline_result.get("artifacts") or {}).items():
        if isinstance(meta, dict) and meta.get("file"):
            arts[key] = meta
    # Ensure sparse entry
    sparse_file = man.get("sparse_file") or "sparse_points.json"
    if (job_dir / sparse_file).is_file():
        arts.setdefault("sparse", {"file": sparse_file})
    if (job_dir / "model.ply").is_file():
        arts.setdefault("splat", {"file": "model.ply"})
    man["artifacts"] = arts
    if pipeline_result.get("ok"):
        if "mesh" in arts:
            man["selected_artifact"] = "mesh"
            man["artifact"] = arts["mesh"]["file"]
        elif "dense" in arts:
            man["selected_artifact"] = "dense"
            man["artifact"] = arts["dense"]["file"]
        man["status"] = "done"
        man.pop("next_action", None)
        man["error"] = None
        if pipeline_result.get("warning"):
            man["alicevision_warning"] = pipeline_result["warning"]
    else:
        man["alicevision_warning"] = pipeline_result.get("warning") or pipeline_result.get("error")
        # Keep sparse usable
        if man.get("status") not in ("done",):
            man["status"] = man.get("status") or "colmap_done"
    man["alicevision_finished_at"] = time.time()
    return normalize_artifacts(man)
