"""Test path traversal protection in ws_detect endpoint.

Verifies that viewer_id is sanitized to prevent path traversal attacks
via WebSocket URL path parameter.
"""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
import sys
sys.path.insert(0, str(_BACKEND))

from api.detect import _sanitize_viewer_id


class TestViewerIdSanitization(unittest.TestCase):
    """Test viewer_id sanitization in ws_detect endpoint."""

    def test_safe_viewer_id_passed_through(self):
        """Safe alphanumeric viewer_id should pass through unchanged."""
        result = _sanitize_viewer_id("viewer123")
        self.assertEqual(result, "viewer123")

    def test_safe_viewer_id_with_underscore(self):
        """Viewer_id with underscore should pass through."""
        result = _sanitize_viewer_id("viewer_456")
        self.assertEqual(result, "viewer_456")

    def test_path_traversal_dotdot_rejected(self):
        """Path traversal with '..' should raise ValueError."""
        with self.assertRaises(ValueError):
            _sanitize_viewer_id("../../etc/passwd")

    def test_path_traversal_slash_rejected(self):
        """Path with '/' should raise ValueError."""
        with self.assertRaises(ValueError):
            _sanitize_viewer_id("viewer/../../etc/passwd")

    def test_path_traversal_backslash_rejected(self):
        """Path with '\\' should raise ValueError."""
        with self.assertRaises(ValueError):
            _sanitize_viewer_id("viewer\\..\\..\\etc\\passwd")

    def test_empty_viewer_id_rejected(self):
        """Empty viewer_id should raise ValueError."""
        with self.assertRaises(ValueError):
            _sanitize_viewer_id("")

    def test_null_bytes_rejected(self):
        """Viewer_id with null bytes should raise ValueError."""
        with self.assertRaises(ValueError):
            _sanitize_viewer_id("viewer\x00../../etc/passwd")


class TestArchiveRelKeyTraversal(unittest.TestCase):
    """Test archive_rel_key path traversal protection in hud_exclusion."""

    def test_normal_video_path(self):
        """Normal archive-relative path should produce stable key."""
        from services.hud_exclusion import archive_rel_key
        result = archive_rel_key("archive/crops/test.jpg")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
        self.assertNotIn("..", result)
        self.assertNotIn("/", result)

    def test_path_traversal_in_video_key(self):
        """Path traversal in source_video should not break cache key."""
        from services.hud_exclusion import archive_rel_key
        result = archive_rel_key("archive/../../../etc/passwd.jpg")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
        # Key should be safe (no path separators or traversal)
        self.assertNotIn("..", result)
        self.assertNotIn("/", result)
        self.assertNotIn("\\", result)

    def test_absolute_path_sanitized_in_key(self):
        """Absolute path should be sanitized in cache key."""
        from services.hud_exclusion import archive_rel_key
        result = archive_rel_key("/etc/passwd")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
        # Should only contain safe characters
        self.assertTrue(all(c.isalnum() or c in "._-" for c in result))


if __name__ == "__main__":
    unittest.main()
