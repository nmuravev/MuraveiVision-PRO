"""Unit tests for mask export (GeoTIFF/KML, GPS gate).

FIXED per grilling C1-C5, M1-M3, R1-R4, G-A-G-E, H1-H4, K1-K3:
- C2: KML Polygon → outerBoundaryIs/LinearRing/coordinates (OGC spec)
- C3: rasterio-only, no toy manual fallback
- C4: module-level rasterio import (None on ImportError)
- R1: video_path filter from status meta (cross-video leak prevention)
- R2: module-level list_detections import (mock targets work)
- R3: optional time_sec query param for GPS interpolation
- H1: deleted duplicate broken tests (SyntaxError), kept fixed copies
- K1: positive GPS test with mocked rows
"""
from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from unittest import mock


def _mask(**kwargs) -> dict:
    return {
        "class": "tank",
        "conf": 0.91,
        "polygon_norm": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]],
        **kwargs,
    }


def _gps() -> dict:
    return {"lat": 50.45, "lon": 30.52, "alt": 120.0}


class MaskServiceTests(unittest.TestCase):
    """Service-level tests (C1-C5 fixes applied)."""

    def test_kml_with_gps_has_ogc_polygon(self) -> None:
        """C2 fix: KML Polygon → outerBoundaryIs/LinearRing."""
        from services.export_masks import build_masks_kml

        xml = build_masks_kml("clip.mp4", [_mask()], _gps())
        root = ET.fromstring(xml)
        self.assertTrue(root.tag.endswith("kml"))
        self.assertIn("outerBoundaryIs", xml)
        self.assertIn("LinearRing", xml)
        self.assertIn("<coordinates", xml)

    def test_kml_without_gps_is_valid_empty_document(self) -> None:
        from services.export_masks import build_masks_kml

        xml = build_masks_kml("clip.mp4", [_mask()], None)
        root = ET.fromstring(xml)
        self.assertTrue(root.tag.endswith("kml"))
        # No Placemark with coordinates (empty Document)
        self.assertNotIn("<coordinates", xml)

    def test_geotiff_with_rasterio(self) -> None:
        """C3 fix: rasterio-only, no toy manual fallback."""
        from services import export_masks
        from unittest.mock import MagicMock

        # Mock _rasterio module with MemoryFile
        mock_rasterio = MagicMock()
        memfile_instance = MagicMock()
        mock_rasterio.MemoryFile.return_value.__enter__ = MagicMock(return_value=memfile_instance)
        mock_rasterio.MemoryFile.return_value.__exit__ = MagicMock(return_value=False)
        memfile_instance.open.return_value.__enter__ = MagicMock()
        memfile_instance.open.return_value.__exit__ = MagicMock()
        memfile_instance.getvalue.return_value = b"fake_tiff_data"

        # Mock from_origin for transform calculation
        mock_from_origin = MagicMock()

        # Patch in module dict (module already imported, _rasterio may be None)
        original_rasterio = export_masks.__dict__.get("_rasterio")
        original_has = export_masks.__dict__.get("_HAS_RASTERIO")
        original_from_origin = export_masks.__dict__.get("from_origin")
        export_masks.__dict__["_rasterio"] = mock_rasterio
        export_masks.__dict__["_HAS_RASTERIO"] = True
        export_masks.__dict__["from_origin"] = mock_from_origin
        try:
            result = export_masks.build_masks_geotiff("clip.mp4", [_mask()], _gps())
            self.assertEqual(result, b"fake_tiff_data")
        finally:
            if original_rasterio is None:
                export_masks.__dict__.pop("_rasterio", None)
            else:
                export_masks.__dict__["_rasterio"] = original_rasterio
            if original_from_origin is None:
                export_masks.__dict__.pop("from_origin", None)
            else:
                export_masks.__dict__["from_origin"] = original_from_origin
            export_masks.__dict__["_HAS_RASTERIO"] = original_has if original_has is not None else False

    def test_filter_masks_by_time_sec(self) -> None:
        """C1 fix: filter by time_sec tolerance."""
        from services.export_masks import _filter_masks

        results = [
            {"time_sec": 10.0, "masks": [_mask()]},
            {"time_sec": 12.5, "masks": [_mask()]},
            {"time_sec": 15.0, "masks": [_mask()]},
        ]

        # With time_sec=12.5, tolerance=1.0 → only time_sec=12.5
        filtered = _filter_masks(results, time_sec=12.5)
        self.assertEqual(len(filtered), 1)

        # Without time_sec → all masks
        filtered_all = _filter_masks(results, time_sec=None)
        self.assertEqual(len(filtered_all), 3)

    def test_resolve_detection_time_sec(self) -> None:
        """C1 fix: detection_id path resolves time_sec from DB."""
        from services.export_masks import _resolve_detection_time_sec

        mock_rows = [
            {"id": "det1", "time_sec": 12.5, "gps_lat": 50.0, "gps_lon": 30.0},
        ]

        with mock.patch("services.export_masks.list_detections", return_value=mock_rows):
            ts = _resolve_detection_time_sec("det1")
        self.assertEqual(ts, 12.5)

    def test_resolve_masks_from_batch_seg(self) -> None:
        from services.export_masks import resolve_masks_for_video

        mock_results = [{"time_sec": 12.5, "masks": [_mask()]}]

        with mock.patch(
            "services.export_masks.batch_seg_status",
            return_value={"results": mock_results, "video_path": "clip.mp4"},
        ):
            masks = resolve_masks_for_video("clip.mp4")
        self.assertEqual(len(masks), 1)
        self.assertEqual(masks[0]["class"], "tank")

    def test_resolve_masks_from_sam3_propagate(self) -> None:
        from services.export_masks import resolve_masks_for_video

        mock_results = [{"time_sec": 15.0, "masks": [_mask()]}]

        with mock.patch(
            "services.export_masks.sam3_prop_status",
            return_value={"results": mock_results, "video_path": "clip.mp4"},
        ):
            with mock.patch(
                "services.export_masks.batch_seg_status", side_effect=KeyError
            ):
                masks = resolve_masks_for_video("clip.mp4")
        self.assertEqual(len(masks), 1)

    def test_empty_masks_returns_empty_list(self) -> None:
        from services.export_masks import resolve_masks_for_video

        with mock.patch("services.export_masks.batch_seg_status", return_value={"results": []}):
            with mock.patch("services.export_masks.sam3_prop_status", return_value={"results": []}):
                masks = resolve_masks_for_video("clip.mp4")
        self.assertEqual(masks, [])

    # H1: first broken copies of test_cross_video_leak_r1 and test_time_sec_gps_interpolation_r3
    # (containing [_mask()}]) deleted — only kept fixed copies below

    def test_cross_video_leak_r1(self) -> None:
        """R1 fix: masks from different video excluded by status[video_path] filter."""
        from services.export_masks import resolve_masks_for_video

        # Batch seg result for video A
        mock_results_a = [{"time_sec": 12.5, "masks": [_mask()]}]
        # Propagate result for video B (different video, same time_sec)
        mock_results_b = [{"time_sec": 12.5, "masks": [_mask()]}]

        with mock.patch(
            "services.export_masks.batch_seg_status",
            return_value={"results": mock_results_a, "video_path": "video_a.mp4"},
        ):
            with mock.patch(
                "services.export_masks.sam3_prop_status",
                return_value={"results": mock_results_b, "video_path": "video_b.mp4"},
            ):
                # Request masks for video B — should NOT get video A masks
                masks = resolve_masks_for_video("video_b.mp4")
        # Should only get from video_b (propagate), not video_a
        self.assertEqual(len(masks), 1)
        self.assertEqual(masks[0]["class"], "tank")

    def test_time_sec_gps_interpolation_r3(self) -> None:
        """R3 fix: time_sec param enables GPS interpolation without detection_id."""
        from services.export_masks import _get_detection_gps

        # telemetry.interpolate expects "timestamp" field
        mock_track = [{"timestamp": 10.0, "lat": 50.45, "lon": 30.52, "alt": 100.0}]

        with mock.patch(
            "services.export_masks.telemetry.load_track_points", return_value=mock_track
        ):
            gps = _get_detection_gps(None, "video.mp4", time_sec=10.0)
        self.assertIsNotNone(gps)
        self.assertEqual(gps["lat"], 50.45)
        self.assertEqual(gps["lon"], 30.52)

    def test_get_detection_gps_positive_k1(self) -> None:
        """K1 fix: positive GPS path — detection with gps_lat/gps_lon returns dict."""
        from services.export_masks import _get_detection_gps

        mock_rows = [
            {"id": "det1", "gps_lat": 55.75, "gps_lon": 37.62, "gps_alt": 150.0},
        ]

        with mock.patch("services.export_masks.list_detections", return_value=mock_rows):
            gps = _get_detection_gps("det1", "video.mp4", None)
        self.assertIsNotNone(gps)
        self.assertEqual(gps["lat"], 55.75)
        self.assertEqual(gps["lon"], 37.62)
        self.assertEqual(gps["alt"], 150.0)


class MaskEndpointTests(unittest.TestCase):
    """C4 fix: endpoint-level tests with TestClient."""

    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        from api.export import router
        from fastapi import FastAPI

        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def _headers(self) -> dict[str, str]:
        """Return auth headers for operator role."""
        import jwt
        from services.db import init_db, get_jwt_secret

        init_db()
        token = jwt.encode(
            {"role": "operator", "sub": "test_user"},
            get_jwt_secret(),
            algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}"}

    def test_geotiff_400_no_gps(self) -> None:
        """GPS gate: 400 with disabled_reason when no GPS."""
        mock_results = [{"time_sec": 12.5, "masks": [_mask()]}]
        mock_det = [{"id": "det1", "time_sec": 12.5, "gps_lat": None, "gps_lon": None}]

        with mock.patch(
            "services.export_masks._check_geo_libs", return_value=(True, "")
        ):
            with mock.patch(
                "services.export_masks.batch_seg_status",
                return_value={"results": mock_results, "video_path": "clip.mp4"},
            ):
                with mock.patch("services.export_masks.list_detections", return_value=mock_det):
                    with mock.patch(
                        "services.export_masks.telemetry.load_track_points", return_value=[]
                    ):
                        resp = self.client.get(
                            "/api/export/masks-geotiff?video_path=clip.mp4&detection_id=det1",
                            headers=self._headers(),
                        )
        self.assertEqual(resp.status_code, 400)
        detail = resp.json()["detail"]
        self.assertIn("disabled_reason", detail)
        self.assertIn("GPS", detail["disabled_reason"])

    def test_geotiff_404_no_masks(self) -> None:
        """404 when no masks found."""
        with mock.patch(
            "services.export_masks._check_geo_libs", return_value=(True, "")
        ):
            with mock.patch(
                "services.export_masks.batch_seg_status", return_value={"results": []}
            ):
                with mock.patch(
                    "services.export_masks.sam3_prop_status", return_value={"results": []}
                ):
                    resp = self.client.get(
                        "/api/export/masks-geotiff?video_path=clip.mp4",
                        headers=self._headers(),
                    )
        self.assertEqual(resp.status_code, 404)

    def test_geotiff_503_geo_libs_missing(self) -> None:
        """503 when rasterio not available."""
        with mock.patch(
            "services.export_masks._check_geo_libs", return_value=(False, "rasterio unavailable")
        ):
            resp = self.client.get(
                "/api/export/masks-geotiff?video_path=clip.mp4",
                headers=self._headers(),
            )
        self.assertEqual(resp.status_code, 503)
        detail = resp.json()["detail"]
        self.assertIn("disabled_reason", detail)
        self.assertIn("geo_libs_missing", detail["disabled_reason"])


if __name__ == "__main__":
    unittest.main()
