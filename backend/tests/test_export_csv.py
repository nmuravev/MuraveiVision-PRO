"""Unit tests for detections CSV export."""
from __future__ import annotations

import unittest
from unittest import mock

from services.export_csv import CSV_COORD_COMMENT, CSV_HEADER, generate_detections_csv


class ExportCsvTests(unittest.TestCase):
    def test_generate_csv_normalized_xyxy(self) -> None:
        rows = [
            {
                "time_sec": 1.5,
                "class_name": "tank",
                "confidence": 0.91,
                "bbox_x": 0.1,
                "bbox_y": 0.2,
                "bbox_w": 0.3,
                "bbox_h": 0.4,
                "gps_lat": 55.75,
                "gps_lon": 37.61,
            },
            {
                "time_sec": 2.0,
                "class_name": "person",
                "confidence": 0.5,
                "bbox_x": 0.0,
                "bbox_y": 0.0,
                "bbox_w": 1.0,
                "bbox_h": 1.0,
                "gps_lat": None,
                "gps_lon": None,
            },
        ]
        with mock.patch("services.export_csv.list_detections", return_value=rows) as ld:
            text = generate_detections_csv("clip.mp4")
        ld.assert_called_once_with("clip.mp4", include_deleted=False)
        self.assertTrue(text.startswith(CSV_COORD_COMMENT))
        lines = text.strip().splitlines()
        self.assertEqual(lines[1], ",".join(CSV_HEADER))
        self.assertIn("tank", lines[2])
        self.assertIn("0.100000", lines[2])  # x1
        self.assertIn("0.400000", lines[2])  # x2 = 0.1+0.3
        self.assertIn("0.600000", lines[2])  # y2 = 0.2+0.4
        self.assertIn("55.75", lines[2])
        self.assertIn("person", lines[3])
        # empty GPS cells leave trailing commas
        self.assertTrue(lines[3].endswith(","))

    def test_generate_csv_empty(self) -> None:
        with mock.patch("services.export_csv.list_detections", return_value=[]):
            text = generate_detections_csv("empty.mp4")
        self.assertIn(CSV_COORD_COMMENT, text)
        self.assertIn("time_sec", text)
        self.assertEqual(len(text.strip().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
