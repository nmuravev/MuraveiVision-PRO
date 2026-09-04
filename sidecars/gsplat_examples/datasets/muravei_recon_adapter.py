"""Adapter: pycolmap.Reconstruction → SceneManager-like API for gsplat examples."""
from __future__ import annotations

import numpy as np


class _Cam:
    def __init__(self, camera) -> None:
        self.camera_type = int(camera.model)
        self.width = int(camera.width)
        self.height = int(camera.height)
        self.fx = float(camera.focal_length_x)
        self.fy = float(camera.focal_length_y)
        self.cx = float(camera.principal_point_x)
        self.cy = float(camera.principal_point_y)
        self.k1 = 0.0
        self.k2 = 0.0
        self.p1 = 0.0
        self.p2 = 0.0
        self.k3 = 0.0
        self.k4 = 0.0
        params = camera.params
        if len(params) >= 1:
            self.k1 = float(params[0])
        if len(params) >= 2:
            self.k2 = float(params[1])
        if len(params) >= 3:
            self.p1 = float(params[2])
        if len(params) >= 4:
            self.p2 = float(params[3])


class _Im:
    def __init__(self, image) -> None:
        self.name = image.name
        self.camera_id = int(image.camera_id)
        rw = image.cam_from_world
        self._rot = np.array(rw.rotation.matrix(), dtype=np.float64)
        self.tvec = np.array(rw.translation, dtype=np.float64)

    def R(self) -> np.ndarray:
        return self._rot


class ReconstructionManager:
    """Minimal SceneManager surface used by gsplat datasets/colmap.Parser."""

    def __init__(self, reconstruction) -> None:
        self._rec = reconstruction
        self.images: dict[int, _Im] = {}
        self.cameras: dict[int, _Cam] = {}
        self.name_to_image_id: dict[str, int] = {}
        self.points3D = np.zeros((0, 3), dtype=np.float32)
        self.point3D_errors = np.zeros((0,), dtype=np.float32)
        self.point3D_colors = np.zeros((0, 3), dtype=np.uint8)
        self.point3D_id_to_point3D_idx: dict[int, int] = {}
        self.point3D_id_to_images: dict[int, list[tuple[int, int]]] = {}

    def load_cameras(self) -> None:
        self.cameras = {int(k): _Cam(v) for k, v in self._rec.cameras.items()}

    def load_images(self) -> None:
        self.images = {}
        self.name_to_image_id = {}
        for image_id, image in self._rec.images.items():
            iid = int(image_id)
            self.images[iid] = _Im(image)
            self.name_to_image_id[image.name] = iid

    def load_points3D(self) -> None:
        pts: list[np.ndarray] = []
        errs: list[float] = []
        colors: list[np.ndarray] = []
        self.point3D_id_to_point3D_idx = {}
        self.point3D_id_to_images = {}

        for idx, (pid, point) in enumerate(self._rec.points3D.items()):
            point_id = int(pid)
            self.point3D_id_to_point3D_idx[point_id] = idx
            pts.append(np.array(point.xyz, dtype=np.float32))
            errs.append(float(point.error))
            colors.append(np.array(point.color, dtype=np.uint8))

        for image_id, image in self._rec.images.items():
            iid = int(image_id)
            for p2d in image.points2D:
                if not p2d.has_point3D():
                    continue
                point_id = int(p2d.point3D_id)
                if point_id not in self.point3D_id_to_point3D_idx:
                    continue
                self.point3D_id_to_images.setdefault(point_id, []).append((iid, 0))

        self.points3D = np.stack(pts, axis=0) if pts else np.zeros((0, 3), dtype=np.float32)
        self.point3D_errors = np.array(errs, dtype=np.float32)
        self.point3D_colors = np.stack(colors, axis=0) if colors else np.zeros((0, 3), dtype=np.uint8)


def load_reconstruction_manager(colmap_dir: str) -> ReconstructionManager:
    import pycolmap

    rec = pycolmap.Reconstruction(colmap_dir)
    manager = ReconstructionManager(rec)
    manager.load_cameras()
    manager.load_images()
    manager.load_points3D()
    return manager
