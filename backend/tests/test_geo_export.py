"""Unit tests for KML / GeoJSON geo export (Stage 1 / 3.3)."""
from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from services.geo_export import _class_color, build_geojson, build_kml


def _det(**kwargs) -> dict:
    base = {
        "id": "d1",
        "class_id": 0,
        "class_name": "tank",
        "confidence": 0.91,
        "time_sec": 12.5,
        "source_video": "clip.mp4",
        "gps_lat": 50.45,
        "gps_lon": 30.52,
        "gps_alt": 120.0,
        "bbox_x": 0.1,
        "bbox_y": 0.2,
        "bbox_w": 0.3,
        "bbox_h": 0.4,
    }
    base.update(kwargs)
    return base


class GeoExportTests(unittest.TestCase):
    def test_kml_is_well_formed_xml(self) -> None:
        xml = build_kml("clip.mp4", detections=[_det()])
        root = ET.fromstring(xml)
        self.assertTrue(root.tag.endswith("kml"))
        self.assertIn("<?xml", xml[:40])
        self.assertIn("30.52,50.45,120.0", xml)  # lon,lat,alt

    def test_kml_escapes_special_chars_in_class_name(self) -> None:
        xml = build_kml(
            "clip.mp4",
            detections=[_det(class_name='tank <alpha> & "beta"')],
        )
        # ElementTree must escape < & " so the XML still parses.
        ET.fromstring(xml)
        self.assertIn("&lt;", xml)
        self.assertIn("&amp;", xml)

    def test_geojson_feature_collection(self) -> None:
        data = build_geojson("clip.mp4", detections=[_det(), _det(id="d2", class_name="truck")])
        self.assertEqual(data["type"], "FeatureCollection")
        self.assertEqual(len(data["features"]), 2)
        feat = data["features"][0]
        self.assertEqual(feat["geometry"]["type"], "Point")
        self.assertEqual(feat["geometry"]["coordinates"][0], 30.52)
        self.assertEqual(feat["geometry"]["coordinates"][1], 50.45)
        self.assertEqual(feat["properties"]["class"], "tank")
        self.assertIn("bbox", feat["properties"])

    def test_collect_skips_detections_without_gps(self) -> None:
        from unittest import mock
        from services.geo_export import collect_geotagged_detections

        rows = [
            _det(),
            _det(id="nogps", gps_lat=None, gps_lon=None),
        ]
        with mock.patch("services.geo_export.list_detections", return_value=rows), \
             mock.patch("services.geo_export.get_flight_track", return_value=None):
            out = collect_geotagged_detections("clip.mp4")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "d1")

    def test_class_color_is_deterministic(self) -> None:
        a = _class_color("military_truck")
        b = _class_color("military_truck")
        c = _class_color("tank")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("#") and len(a) == 7)
        # Different classes may collide in a 10-color palette; just assert format.
        self.assertTrue(c.startswith("#") and len(c) == 7)

    def test_kml_style_id_stable_across_calls(self) -> None:
        xml1 = build_kml("clip.mp4", detections=[_det()])
        xml2 = build_kml("clip.mp4", detections=[_det()])
        # styleUrl must match Style id in both documents identically.
        root1 = ET.fromstring(xml1)
        root2 = ET.fromstring(xml2)
        ns = {"k": "http://www.opengis.net/kml/2.2"}
        url1 = root1.find(".//k:styleUrl", ns)
        url2 = root2.find(".//k:styleUrl", ns)
        self.assertIsNotNone(url1)
        self.assertEqual(url1.text, url2.text)


if __name__ == "__main__":
    unittest.main()
