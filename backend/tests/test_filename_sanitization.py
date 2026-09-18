"""Test P1-6: Filename sanitization in network_attachments.

Verifies that filename is sanitized to prevent path traversal attacks.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))

from services import network_attachments


class TestFilenameSanitization(unittest.TestCase):
    """Test P1-6 filename sanitization."""

    def test_safe_filename_accepted(self):
        """Normal filename should be accepted."""
        meta = network_attachments.init_attachment(
            filename="photo.jpg",
            content_type="image/jpeg",
            size=1024,
            sha256="a" * 64,
        )
        self.assertEqual(meta["filename"], "photo.jpg")

    def test_path_traversal_dotdot_rejected(self):
        """Filename with '..' should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            network_attachments.init_attachment(
                filename="../../../etc/passwd.jpg",
                content_type="image/jpeg",
                size=1024,
                sha256="a" * 64,
            )
        self.assertIn("path traversal", str(ctx.exception).lower())

    def test_path_traversal_slash_rejected(self):
        """Filename with '/' should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            network_attachments.init_attachment(
                filename="subdir/file.jpg",
                content_type="image/jpeg",
                size=1024,
                sha256="a" * 64,
            )
        self.assertIn("path traversal", str(ctx.exception).lower())

    def test_path_traversal_backslash_rejected(self):
        """Filename with '\\' should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            network_attachments.init_attachment(
                filename="subdir\\file.jpg",
                content_type="image/jpeg",
                size=1024,
                sha256="a" * 64,
            )
        self.assertIn("path traversal", str(ctx.exception).lower())

    def test_filename_truncated_to_200_chars(self):
        """Filename should be truncated to 200 chars."""
        long_name = "a" * 300 + ".jpg"
        meta = network_attachments.init_attachment(
            filename=long_name,
            content_type="image/jpeg",
            size=1024,
            sha256="a" * 64,
        )
        self.assertEqual(len(meta["filename"]), 200)


if __name__ == "__main__":
    unittest.main()
