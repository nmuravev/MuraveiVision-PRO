"""geo_import: missing SRT/CSV is 200, not 404."""
from __future__ import annotations

import asyncio
import unittest
from unittest import mock

from api import geo as geo_api
from api.geo import GeoImportBody


class GeoImportMissingSidecarTests(unittest.TestCase):
    def _run_import(self) -> dict:
        return asyncio.run(
            geo_api.geo_import(
                GeoImportBody(video_path="archive/dji_nosrt.mp4"),
                _user={"role": "operator"},
            )
        )

    def test_no_sidecar_returns_200_sidecar_missing(self) -> None:
        with mock.patch.object(geo_api.telemetry, "ensure_track_for_video", return_value=[]):
            with mock.patch.object(geo_api.telemetry, "find_sidecar", return_value=None):
                with mock.patch.object(geo_api.telemetry, "backfill_detection_gps", return_value=0):
                    out = self._run_import()
        self.assertEqual(out["point_count"], 0)
        self.assertTrue(out["sidecar_missing"])
        self.assertEqual(out["points"], [])
        self.assertIsNone(out["source_file"])

    def test_file_not_found_is_empty_not_http_404(self) -> None:
        with mock.patch.object(
            geo_api.telemetry,
            "ensure_track_for_video",
            side_effect=FileNotFoundError("Sidecar .SRT/.CSV не найден"),
        ):
            with mock.patch.object(geo_api.telemetry, "find_sidecar", return_value=None):
                with mock.patch.object(geo_api.telemetry, "backfill_detection_gps", return_value=0):
                    out = self._run_import()
        self.assertEqual(out["point_count"], 0)
        self.assertTrue(out["sidecar_missing"])


if __name__ == "__main__":
    unittest.main()
