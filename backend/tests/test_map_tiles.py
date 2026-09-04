"""Unit tests for offline map tile service."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import map_tiles as mt


class MapTilesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = Path(tempfile.mkdtemp())
        self._tiles = self._tmp / "map_tiles"
        self._mb = self._tmp / "map_tiles.mbtiles"
        self._prev_dir = mt.TILES_DIR
        self._prev_mb = mt.MBTILES_PATH
        mt.TILES_DIR = self._tiles
        mt.MBTILES_PATH = self._mb

    def tearDown(self) -> None:
        mt.TILES_DIR = self._prev_dir
        mt.MBTILES_PATH = self._prev_mb
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_tiles_available_false_empty(self) -> None:
        self.assertFalse(mt.tiles_available())

    def test_get_tile_from_folder(self) -> None:
        path = self._tiles / "14" / "100"
        path.mkdir(parents=True)
        (path / "200.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
        self.assertTrue(mt.tiles_available())
        data = mt.get_tile_bytes(14, 100, 200)
        self.assertEqual(data, b"\x89PNG\r\n\x1a\nfake")

    def test_get_tile_missing(self) -> None:
        self._tiles.mkdir(parents=True)
        self.assertIsNone(mt.get_tile_bytes(14, 100, 200))

    def test_get_tile_from_mbtiles_tms(self) -> None:
        conn = sqlite3.connect(self._mb)
        conn.execute(
            "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)"
        )
        z, x, y_xyz = 14, 100, 200
        y_tms = (2**z - 1) - y_xyz
        conn.execute(
            "INSERT INTO tiles VALUES (?,?,?,?)",
            (z, x, y_tms, b"mb-png"),
        )
        conn.commit()
        conn.close()
        self.assertTrue(mt.tiles_available())
        self.assertEqual(mt.get_tile_bytes(z, x, y_xyz), b"mb-png")

    def test_invalid_coords(self) -> None:
        self.assertIsNone(mt.get_tile_bytes(-1, 0, 0))
        self.assertIsNone(mt.get_tile_bytes(23, 0, 0))


class MapApiTests(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        from main import app

        self.client = TestClient(app)
        self._tmp = Path(tempfile.mkdtemp())
        self._tiles = self._tmp / "map_tiles"
        self._prev_dir = mt.TILES_DIR
        self._prev_mb = mt.MBTILES_PATH
        mt.TILES_DIR = self._tiles
        mt.MBTILES_PATH = self._tmp / "missing.mbtiles"

    def tearDown(self) -> None:
        mt.TILES_DIR = self._prev_dir
        mt.MBTILES_PATH = self._prev_mb
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_status_no_tiles(self) -> None:
        res = self.client.get("/api/map/status")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"tiles_available": False})

    def test_get_tile_success(self) -> None:
        path = self._tiles / "14" / "100"
        path.mkdir(parents=True)
        (path / "200.png").write_bytes(b"\x89PNG\r\n\x1a\nok")
        res = self.client.get("/api/map/tiles/14/100/200.png")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("content-type"), "image/png")
        self.assertEqual(res.content, b"\x89PNG\r\n\x1a\nok")

    def test_get_tile_404(self) -> None:
        self._tiles.mkdir(parents=True)
        res = self.client.get("/api/map/tiles/14/100/200.png")
        self.assertEqual(res.status_code, 404)

    def test_get_tile_400(self) -> None:
        res = self.client.get("/api/map/tiles/-1/0/0.png")
        self.assertEqual(res.status_code, 400)


class ChangeExportMapTests(unittest.TestCase):
    def test_html_no_osm_cdn_when_tiles_missing(self) -> None:
        from services.change_export import build_change_html

        with mock.patch("services.map_tiles.tiles_available", return_value=False):
            html = build_change_html(
                {
                    "method": "gps",
                    "summary": {},
                    "new": [
                        {
                            "class_name": "truck",
                            "bbox": {"x1": 0, "y1": 0, "x2": 1, "y2": 1},
                            "gps_lat": 55.0,
                            "gps_lon": 37.0,
                        }
                    ],
                    "removed": [],
                    "matches": [],
                    "message": None,
                },
                {"video_before": "a.mp4", "video_after": "b.mp4", "time_before": 1, "time_after": 2},
            )
        self.assertNotIn("tile.openstreetmap.org", html)
        self.assertIn("Тайлы не установлены", html)

    def test_html_uses_local_tiles_when_available(self) -> None:
        from services.change_export import build_change_html

        with mock.patch("services.map_tiles.tiles_available", return_value=True):
            html = build_change_html(
                {
                    "method": "gps",
                    "summary": {},
                    "new": [
                        {
                            "class_name": "truck",
                            "bbox": {"x1": 0, "y1": 0, "x2": 1, "y2": 1},
                            "gps_lat": 55.0,
                            "gps_lon": 37.0,
                        }
                    ],
                    "removed": [],
                    "matches": [],
                    "message": None,
                },
                {"video_before": "a.mp4", "video_after": "b.mp4", "time_before": 1, "time_after": 2},
            )
        self.assertNotIn("tile.openstreetmap.org", html)
        self.assertIn("/api/map/tiles/{z}/{x}/{y}.png", html)
        self.assertIn("Офлайн карта", html)


if __name__ == "__main__":
    unittest.main()
