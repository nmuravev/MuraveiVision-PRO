from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.colmap_poses import _parse_cameras_txt, _parse_images_txt, _quat_to_rot, nearest_pose


class ColmapPoseTests(unittest.TestCase):
    def test_camera_model_parameter_orders(self) -> None:
        text = "\n".join(
            [
                "1 PINHOLE 1920 1080 1000 900 960 540",
                "2 SIMPLE_PINHOLE 1920 1080 800 950 530",
                "3 SIMPLE_RADIAL 1920 1080 700 940 520 0.01",
                "4 RADIAL 1920 1080 600 930 510 0.01 0.001",
                "5 OPENCV 1920 1080 1100 1050 970 550 0 0 0 0",
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cameras.txt"
            path.write_text(text, encoding="utf-8")
            cameras = _parse_cameras_txt(path)

        self.assertEqual(
            cameras[1]["intrinsics"],
            {"fx": 1000.0, "fy": 900.0, "cx": 960.0, "cy": 540.0},
        )
        self.assertEqual(
            cameras[2]["intrinsics"],
            {"fx": 800.0, "fy": 800.0, "cx": 950.0, "cy": 530.0},
        )
        self.assertEqual(
            cameras[3]["intrinsics"],
            {"fx": 700.0, "fy": 700.0, "cx": 940.0, "cy": 520.0},
        )
        self.assertEqual(
            cameras[4]["intrinsics"],
            {"fx": 600.0, "fy": 600.0, "cx": 930.0, "cy": 510.0},
        )
        self.assertEqual(
            cameras[5]["intrinsics"],
            {"fx": 1100.0, "fy": 1050.0, "cx": 970.0, "cy": 550.0},
        )

    def test_identity_quaternion_and_nearest_pose(self) -> None:
        self.assertEqual(
            _quat_to_rot(1, 0, 0, 0),
            [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        )
        doc = {"frames": [{"time_sec": 1.0}, {"time_sec": 3.0}]}
        self.assertEqual(nearest_pose(doc, 2.6), {"time_sec": 3.0})

    def test_images_txt_skips_points2d_float_lines(self) -> None:
        text = "\n".join(
            [
                "# comment",
                "1 1 0 0 0 0 0 0 1 000001.jpg",
                "10.5 20.5 -1 11.5 21.5 2 12.0 22.0 -1",
                "2 1 0 0 0 1 2 3 1 000002.jpg",
                "1.0 2.0 -1",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "images.txt"
            path.write_text(text, encoding="utf-8")
            images = _parse_images_txt(path)
        self.assertEqual([im["image"] for im in images], ["000001.jpg", "000002.jpg"])


if __name__ == "__main__":
    unittest.main()
