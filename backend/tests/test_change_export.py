"""P3.15.3: change detection HTML/KML export formatters."""
from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET

from services.change_export import build_change_html
from services.geo_export import build_change_kml


def _sample_result(*, with_gps: bool = True) -> dict:
    gps = {"gps_lat": 55.75, "gps_lon": 37.61} if with_gps else {}
    return {
        "method": "gps",
        "aligned": True,
        "message": None,
        "summary": {
            "total_before": 2,
            "total_after": 2,
            "matched": 1,
            "stable": 0,
            "moved": 1,
            "new": 1,
            "removed": 1,
        },
        "new": [
            {
                "id": "n1",
                "class_name": "trench",
                "confidence": 0.91,
                "bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2},
                **gps,
            }
        ],
        "removed": [
            {
                "id": "r1",
                "class_name": "person",
                "confidence": 0.8,
                "bbox": {"x1": 0.3, "y1": 0.3, "x2": 0.4, "y2": 0.4},
                **gps,
            }
        ],
        "matches": [
            {
                "before_id": "b1",
                "after_id": "a1",
                "class_name": "car",
                "distance_m": 5.2,
                "status": "moved",
                "before_bbox": {"x1": 0.5, "y1": 0.5, "x2": 0.6, "y2": 0.6},
                "after_bbox": {"x1": 0.55, "y1": 0.55, "x2": 0.65, "y2": 0.65},
                **({"gps_lat": 55.751, "gps_lon": 37.611} if with_gps else {}),
            }
        ],
        "image_diff": None,
    }


_META = {
    "video_before": "a.mp4",
    "video_after": "b.mp4",
    "time_before": 12.0,
    "time_after": 8.0,
    "generated_at": "2026-09-02T12:00:00+00:00",
}


class ChangeHtmlExportTests(unittest.TestCase):
    def test_build_change_html_contains_summary(self) -> None:
        html = build_change_html(_sample_result(), _META)
        self.assertIn("Отчёт изменений", html)
        self.assertIn("Новые", html)
        self.assertIn("Исчезли", html)
        self.assertIn("Перемещены", html)
        self.assertIn("trench", html)
        self.assertIn(">1</td>", html)  # summary new/moved/removed counts appear
        self.assertIn("a.mp4", html)
        self.assertIn("b.mp4", html)


class ChangeKmlExportTests(unittest.TestCase):
    def test_build_change_kml_placemarks(self) -> None:
        xml = build_change_kml(_sample_result(with_gps=True), _META)
        root = ET.fromstring(xml)
        ns = {"k": "http://www.opengis.net/kml/2.2"}
        folders = root.findall(".//k:Folder", ns)
        self.assertEqual(len(folders), 3)
        names = [f.findtext("k:name", default="", namespaces=ns) for f in folders]
        self.assertEqual(names, ["New", "Removed", "Moved"])
        placemarks = root.findall(".//k:Placemark", ns)
        self.assertGreaterEqual(len(placemarks), 3)
        coords = root.findtext(".//k:coordinates", default="", namespaces=ns)
        self.assertIn("37.61", coords)

    def test_build_change_kml_no_gps(self) -> None:
        xml = build_change_kml(_sample_result(with_gps=False), _META)
        root = ET.fromstring(xml)
        ns = {"k": "http://www.opengis.net/kml/2.2"}
        doc = root.find("k:Document", ns)
        self.assertIsNotNone(doc)
        self.assertTrue(doc.findtext("k:name", default="", namespaces=ns))
        placemarks = root.findall(".//k:Placemark", ns)
        self.assertEqual(len(placemarks), 0)
        folders = root.findall(".//k:Folder", ns)
        self.assertEqual(len(folders), 3)


if __name__ == "__main__":
    unittest.main()
