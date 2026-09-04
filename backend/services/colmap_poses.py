"""Parse COLMAP sparse model → camera_poses.json for 2D→3D raycast."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _quat_to_rot(qw: float, qx: float, qy: float, qz: float) -> list[list[float]]:
    """COLMAP qvec → 3×3 rotation (world-to-camera)."""
    norm = math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz) or 1.0
    qw, qx, qy, qz = qw / norm, qx / norm, qy / norm, qz / norm
    return [
        [
            1 - 2 * qy * qy - 2 * qz * qz,
            2 * qx * qy - 2 * qz * qw,
            2 * qx * qz + 2 * qy * qw,
        ],
        [
            2 * qx * qy + 2 * qz * qw,
            1 - 2 * qx * qx - 2 * qz * qz,
            2 * qy * qz - 2 * qx * qw,
        ],
        [
            2 * qx * qz - 2 * qy * qw,
            2 * qy * qz + 2 * qx * qw,
            1 - 2 * qx * qx - 2 * qy * qy,
        ],
    ]


def _parse_cameras_txt(path: Path) -> dict[int, dict[str, Any]]:
    cams: dict[int, dict[str, Any]] = {}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        cam_id = int(parts[0])
        model = parts[1].upper()
        width = int(float(parts[2]))
        height = int(float(parts[3]))
        params = [float(p) for p in parts[4:]]
        intr: dict[str, float] = {}
        # COLMAP model parameter order:
        # PINHOLE/OPENCV/FULL_OPENCV = fx, fy, cx, cy, ...
        # SIMPLE_PINHOLE/SIMPLE_RADIAL/RADIAL = f, cx, cy, ...
        if model in ("PINHOLE", "OPENCV", "FULL_OPENCV") and len(params) >= 4:
            intr = {"fx": params[0], "fy": params[1], "cx": params[2], "cy": params[3]}
        elif model in ("SIMPLE_PINHOLE", "SIMPLE_RADIAL", "RADIAL") and len(params) >= 3:
            intr = {"fx": params[0], "fy": params[0], "cx": params[1], "cy": params[2]}
        else:
            # Fallback: assume first param is focal
            f = params[0] if params else max(width, height)
            intr = {"fx": f, "fy": f, "cx": width / 2.0, "cy": height / 2.0}
        cams[cam_id] = {
            "model": model,
            "image_size": {"width": width, "height": height},
            "intrinsics": intr,
        }
    return cams


def _parse_images_txt(path: Path) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 10:
            continue
        qw, qx, qy, qz = (float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4]))
        tx, ty, tz = float(parts[5]), float(parts[6]), float(parts[7])
        cam_id = int(parts[8])
        name = parts[9]
        R = _quat_to_rot(qw, qx, qy, qz)
        images.append(
            {
                "image_id": int(parts[0]),
                "camera_id": cam_id,
                "image": name,
                "R": R,
                "t": [tx, ty, tz],
            }
        )
        # skip POINTS2D line
        if i < len(lines) and not lines[i].strip().startswith("#"):
            i += 1
    return images


def export_camera_poses(
    sparse_dir: Path,
    out_path: Path,
    *,
    frame_times: dict[str, float],
    t_start: float = 0.0,
    fps_sample: float = 1.0,
    hud_crop: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Build camera_poses.json from COLMAP sparse/0 text model."""
    from services.hud_exclusion import map_intrinsics_to_full_frame

    sparse_dir = Path(sparse_dir)
    cameras_txt = sparse_dir / "cameras.txt"
    images_txt = sparse_dir / "images.txt"
    if not cameras_txt.is_file() or not images_txt.is_file():
        raise FileNotFoundError(f"COLMAP text model missing in {sparse_dir}")

    cameras = _parse_cameras_txt(cameras_txt)
    images = _parse_images_txt(images_txt)
    full_w = int((hud_crop or {}).get("full_width") or 0)
    full_h = int((hud_crop or {}).get("full_height") or 0)
    frames: list[dict[str, Any]] = []
    for idx, img in enumerate(sorted(images, key=lambda x: x["image"])):
        cam = cameras.get(img["camera_id"], {})
        intr = cam.get("intrinsics") or {"fx": 1000.0, "fy": 1000.0, "cx": 960.0, "cy": 540.0}
        size = cam.get("image_size") or {"width": 1920, "height": 1080}
        if hud_crop and full_w > 0 and full_h > 0:
            intr, size = map_intrinsics_to_full_frame(intr, size, hud_crop, full_w, full_h)
        name = img["image"]
        time_sec = frame_times.get(name)
        if time_sec is None:
            time_sec = t_start + idx / max(0.1, fps_sample)
        frames.append(
            {
                "frame_idx": idx,
                "time_sec": round(float(time_sec), 4),
                "image": name,
                "image_size": size,
                "R": img["R"],
                "t": img["t"],
                "intrinsics": intr,
            }
        )

    payload: dict[str, Any] = {
        "coordinate_convention": "colmap_world_to_camera",
        "note": "x_cam = R @ X_world + t; ray: dir_world = R^T @ dir_cam, origin = -R^T @ t",
        "t_start": t_start,
        "fps_sample": fps_sample,
        "frames": frames,
    }
    if hud_crop:
        payload["hud_crop"] = {
            "top": float(hud_crop.get("top") or 0),
            "bottom": float(hud_crop.get("bottom") or 0),
            "left": float(hud_crop.get("left") or 0),
            "right": float(hud_crop.get("right") or 0),
        }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def nearest_pose(poses_doc: dict[str, Any], time_sec: float) -> dict[str, Any] | None:
    frames = poses_doc.get("frames") or []
    if not frames:
        return None
    best = min(frames, key=lambda f: abs(float(f.get("time_sec", 0)) - time_sec))
    return best


def export_sparse_points(sparse_dir: Path, out_path: Path, max_points: int = 80000) -> int:
    """Export COLMAP points3D.txt → lightweight JSON for scene preview + raycast fallback."""
    pts_file = Path(sparse_dir) / "points3D.txt"
    if not pts_file.is_file():
        return 0
    points: list[list[float]] = []
    for line in pts_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
        points.append([x, y, z])
        if len(points) >= max_points:
            break
    payload = {"count": len(points), "points": points}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload), encoding="utf-8")
    return len(points)
