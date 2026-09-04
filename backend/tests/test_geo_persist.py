"""P0.4: persist interpolated GPS on detections + backfill."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from services import db
from services import telemetry


class GeoPersistTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._orig_path = db.DB_PATH
        self._orig_init = db._initialized
        db.DB_PATH = Path(self._tmp.name)
        db._initialized = False
        db.init_db()
        self.video = "archive/geo_persist/clip.mp4"
        db.upsert_flight_track(
            self.video,
            [
                {"timestamp": 0.0, "lat": 55.75, "lon": 37.61, "alt": 40.0},
                {"timestamp": 10.0, "lat": 55.76, "lon": 37.62, "alt": 50.0},
            ],
            source_file="clip.srt",
        )

    def tearDown(self) -> None:
        db.DB_PATH = self._orig_path
        db._initialized = False
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def test_attach_gps_interpolates_midpoint(self) -> None:
        payload = telemetry.attach_gps(
            {
                "source_video": self.video,
                "time_sec": 5.0,
                "class_name": "tank",
            }
        )
        self.assertAlmostEqual(float(payload["gps_lat"]), 55.755, places=5)
        self.assertAlmostEqual(float(payload["gps_lon"]), 37.615, places=5)
        self.assertAlmostEqual(float(payload["gps_alt"]), 45.0, places=5)

    def test_attach_gps_keeps_explicit_coords(self) -> None:
        payload = telemetry.attach_gps(
            {
                "source_video": self.video,
                "time_sec": 5.0,
                "gps_lat": 1.0,
                "gps_lon": 2.0,
                "gps_alt": 3.0,
            }
        )
        self.assertEqual(payload["gps_lat"], 1.0)
        self.assertEqual(payload["gps_lon"], 2.0)

    def test_attach_gps_noop_without_track(self) -> None:
        payload = telemetry.attach_gps(
            {"source_video": "archive/missing/none.mp4", "time_sec": 1.0}
        )
        self.assertNotIn("gps_lat", payload)

    def test_insert_via_attach_persists(self) -> None:
        row = db.insert_detection(
            telemetry.attach_gps(
                {
                    "source_video": self.video,
                    "time_sec": 2.0,
                    "class_name": "soldier",
                    "bbox_x": 0.1,
                    "bbox_y": 0.1,
                    "bbox_w": 0.2,
                    "bbox_h": 0.2,
                    "origin": "auto",
                }
            )
        )
        stored = db.get_detection(row["id"])
        assert stored is not None
        self.assertIsNotNone(stored.get("gps_lat"))
        self.assertIsNotNone(stored.get("gps_lon"))

    def test_backfill_fills_null_gps_only(self) -> None:
        empty = db.insert_detection(
            {
                "source_video": self.video,
                "time_sec": 4.0,
                "class_name": "tank",
                "bbox_x": 0.1,
                "bbox_y": 0.1,
                "bbox_w": 0.2,
                "bbox_h": 0.2,
                "origin": "manual",
            }
        )
        kept = db.insert_detection(
            {
                "source_video": self.video,
                "time_sec": 8.0,
                "class_name": "truck",
                "bbox_x": 0.2,
                "bbox_y": 0.2,
                "bbox_w": 0.2,
                "bbox_h": 0.2,
                "origin": "manual",
                "gps_lat": 10.0,
                "gps_lon": 20.0,
                "gps_alt": 1.0,
            }
        )
        n = telemetry.backfill_detection_gps(self.video)
        self.assertEqual(n, 1)
        filled = db.get_detection(empty["id"])
        assert filled is not None
        self.assertAlmostEqual(float(filled["gps_lat"]), 55.754, places=3)
        same = db.get_detection(kept["id"])
        assert same is not None
        self.assertEqual(same["gps_lat"], 10.0)
        self.assertEqual(telemetry.backfill_detection_gps(self.video), 0)
