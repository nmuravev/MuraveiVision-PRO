"""P1-3: SQL injection via dynamic column names — strict whitelist validation."""
import os
import sys
import tempfile
import shutil
import unittest

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.services import db


def _make_detection_payload(**overrides):
    """Helper to create a full detection payload with defaults."""
    base = {
        "time_sec": 10.0,
        "class_name": "test",
        "bbox_x": 0.1,
        "bbox_y": 0.2,
        "bbox_w": 0.3,
        "bbox_h": 0.4,
    }
    base.update(overrides)
    return base


class TestSQLInjectionWhitelist(unittest.TestCase):
    """Verify that update_detection rejects SQL injection attempts in column names."""

    def setUp(self):
        """Create a temporary directory for the database to avoid polluting test DB."""
        self.test_dir = tempfile.mkdtemp()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.test_dir, "test_muravei.db")
        db._initialized = False
        db._jwt_secret_cache = None
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        db._initialized = False
        db._jwt_secret_cache = None
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_injection_in_column_name_rejected(self):
        """SQL injection attempt via column name should be rejected."""
        payload = {
            "class_name": "test",
            "user_notes'; DROP TABLE detections; --": "malicious",
        }
        # Should not raise — just skip unknown fields
        result = db.update_detection("nonexistent-id", payload)
        self.assertIsNone(result)

    def test_injection_with_union_select_rejected(self):
        """Classic UNION SELECT injection in field name."""
        payload = {
            "class_name": "test",
            "class_name' UNION SELECT * FROM pins --": "hacked",
        }
        result = db.update_detection("nonexistent-id", payload)
        self.assertIsNone(result)

    def test_boolean_injection_rejected(self):
        """Injection trying to use boolean-like names."""
        payload = {
            "class_name": "test",
            "1=1": "malicious",
            "is_deleted": True,
        }
        # Only is_deleted should be applied
        det_id = "injection-test-1"
        db.insert_detection(_make_detection_payload(id=det_id))
        result = db.update_detection(det_id, payload)
        self.assertIsNotNone(result)
        self.assertTrue(result["is_deleted"])
        self.assertEqual(result["class_name"], "test")  # class_name not updated

    def test_only_whitelisted_fields_applied(self):
        """Only fields in whitelist should be applied."""
        det_id = "whitelist-test-1"
        db.insert_detection(_make_detection_payload(id=det_id, class_name="before", confidence=0.5))
        payload = {
            "class_name": "after",
            "confidence": 0.95,
            "fake_column": "should_be_ignored",
            "another_fake": 12345,
        }
        result = db.update_detection(det_id, payload)
        self.assertEqual(result["class_name"], "after")
        self.assertAlmostEqual(result["confidence"], 0.95)

    def test_type_coercion_enforced(self):
        """Type coercion should be enforced per column."""
        det_id = "type-test-1"
        db.insert_detection(_make_detection_payload(id=det_id, class_name="test"))
        # class_id expects int — passing string should be coerced
        result = db.update_detection(det_id, {"class_id": "42"})
        self.assertIsNotNone(result)
        self.assertEqual(result["class_id"], 42)

    def test_empty_fields_dict_returns_detection(self):
        """Empty fields dict should return detection unchanged."""
        det_id = "empty-test-1"
        db.insert_detection(_make_detection_payload(id=det_id, class_name="unchanged"))
        result = db.update_detection(det_id, {})
        self.assertIsNotNone(result)
        self.assertEqual(result["class_name"], "unchanged")


if __name__ == "__main__":
    unittest.main()
