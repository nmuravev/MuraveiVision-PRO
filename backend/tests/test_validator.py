from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import services.response_validator as rv_mod
from services.response_validator import ResponseValidator, ValidationResult


def _det(bbox=None, confidence=0.8, class_id=5):
    if bbox is None:
        bbox = {"x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.3}
    return {
        "id": "trk-1",
        "class_id": class_id,
        "class_en": "tank",
        "class_ru": "tank",
        "confidence": confidence,
        "bbox": bbox,
        "color": "#ef4444",
        "origin": "auto",
        "track_id": 1,
    }


class ValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        # Fresh validator with a known catalog: ids 5 and 7 enabled, 99 disabled.
        self.validator = ResponseValidator()
        catalog = [
            {"id": 5, "name_en": "tank", "enabled": True},
            {"id": 7, "name_en": "military_truck", "enabled": True},
            {"id": 99, "name_en": "disabled_class", "enabled": False},
        ]
        self.validator._enabled_ids = {5, 7}

        # Redirect log file to a temp path so tests don't pollute real logs.
        self._tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        self._tmp.close()
        self._log_path = Path(self._tmp.name)
        self._orig_log_file = rv_mod.LOG_FILE
        rv_mod.LOG_FILE = self._log_path

    def tearDown(self) -> None:
        rv_mod.LOG_FILE = self._orig_log_file
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    # --- validate_detection ---
    def test_valid_detection_passes(self) -> None:
        res = self.validator.validate_detection(_det())
        self.assertTrue(res.passed)
        self.assertEqual(res.reasons, [])

    def test_invalid_bbox_x2_lt_x1_rejected(self) -> None:
        det = _det(bbox={"x1": 0.3, "y1": 0.1, "x2": 0.1, "y2": 0.3})
        res = self.validator.validate_detection(det)
        self.assertFalse(res.passed)
        self.assertTrue(any("degenerate" in r for r in res.reasons))

    def test_bbox_out_of_range_rejected(self) -> None:
        det = _det(bbox={"x1": -0.1, "y1": 0.1, "x2": 0.3, "y2": 0.3})
        res = self.validator.validate_detection(det)
        self.assertFalse(res.passed)
        self.assertTrue(any("out of [0,1]" in r for r in res.reasons))

    def test_confidence_out_of_range_rejected(self) -> None:
        for bad_conf in (0.001, 1.5):
            det = _det(confidence=bad_conf)
            res = self.validator.validate_detection(det)
            self.assertFalse(res.passed, f"conf={bad_conf} should reject")
            self.assertTrue(any("confidence" in r for r in res.reasons))

    def test_bbox_too_small_rejected(self) -> None:
        det = _det(bbox={"x1": 0.1, "y1": 0.1, "x2": 0.1001, "y2": 0.1001})
        res = self.validator.validate_detection(det)
        self.assertFalse(res.passed)
        self.assertTrue(any("area" in r and "min" in r for r in res.reasons))

    def test_bbox_too_large_rejected(self) -> None:
        det = _det(bbox={"x1": 0.0, "y1": 0.0, "x2": 0.99, "y2": 0.99})
        res = self.validator.validate_detection(det)
        self.assertFalse(res.passed)
        self.assertTrue(any("area" in r and "max" in r for r in res.reasons))

    def test_unknown_class_id_rejected(self) -> None:
        det = _det(class_id=12345)
        res = self.validator.validate_detection(det)
        self.assertFalse(res.passed)
        self.assertTrue(any("class_id" in r for r in res.reasons))

    def test_disabled_class_id_rejected(self) -> None:
        # id 99 is in catalog but disabled → not in enabled_ids set.
        det = _det(class_id=99)
        res = self.validator.validate_detection(det)
        self.assertFalse(res.passed)
        self.assertTrue(any("class_id" in r for r in res.reasons))

    def test_bbox_missing_rejected(self) -> None:
        det = _det()
        det["bbox"] = None
        res = self.validator.validate_detection(det)
        self.assertFalse(res.passed)

    # --- validate_batch ---
    def test_batch_filters_correctly(self) -> None:
        good = _det()
        bad = _det(bbox={"x1": 0.5, "y1": 0.5, "x2": 0.5, "y2": 0.5})  # zero area
        out = self.validator.validate_batch([good, bad])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["class_id"], 5)

    def test_batch_logs_rejections_to_jsonl(self) -> None:
        bad = _det(bbox={"x1": 0.5, "y1": 0.5, "x2": 0.5, "y2": 0.5})
        self.validator.validate_batch([bad])
        self.assertTrue(self._log_path.exists())
        lines = self._log_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertIn("ts", entry)
        self.assertIn("detection", entry)
        self.assertIn("reasons", entry)
        self.assertIsInstance(entry["reasons"], list)
        self.assertTrue(len(entry["reasons"]) > 0)

    def test_disabled_validator_passes_all(self) -> None:
        bad = _det(bbox={"x1": 0.5, "y1": 0.5, "x2": 0.5, "y2": 0.5})
        with mock.patch.object(self.validator, "_enabled", return_value=False):
            out = self.validator.validate_batch([bad])
        self.assertEqual(out, [bad])

    def test_graceful_degradation_on_exception(self) -> None:
        bad = _det(bbox={"x1": 0.5, "y1": 0.5, "x2": 0.5, "y2": 0.5})
        with mock.patch.object(
            self.validator, "validate_detection", side_effect=RuntimeError("boom")
        ):
            out = self.validator.validate_batch([bad])
        # On validator error, original list is returned unchanged.
        self.assertEqual(out, [bad])

    def test_graceful_degradation_on_catalog_failure(self) -> None:
        # Empty known_ids simulates catalog load failure → all accepted.
        v = ResponseValidator()
        v._enabled_ids = set()
        bad = _det(bbox={"x1": 0.5, "y1": 0.5, "x2": 0.5, "y2": 0.5})
        out = v.validate_batch([bad])
        self.assertEqual(out, [bad])

    def test_validation_result_dataclass(self) -> None:
        r_ok = ValidationResult(passed=True)
        self.assertEqual(r_ok.reasons, [])
        r_bad = ValidationResult(passed=False, reasons=["x"])
        self.assertFalse(r_bad.passed)
        self.assertEqual(r_bad.reasons, ["x"])


if __name__ == "__main__":
    unittest.main()
