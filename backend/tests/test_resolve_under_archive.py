# KEEP: session trace — do not remove without explicit user order
"""resolve_under_archive path confinement."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from services import security as sec


class ResolveUnderArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "archive"
        self.root.mkdir(parents=True)
        (self.root / "crops").mkdir()
        (self.root / "crops" / "abc.jpg").write_bytes(b"x")
        self._orig = sec.BASE_DIR
        sec.BASE_DIR = Path(self._tmp.name)

    def tearDown(self) -> None:
        sec.BASE_DIR = self._orig
        self._tmp.cleanup()

    def test_relative_crops(self) -> None:
        p = sec.resolve_under_archive("crops/abc.jpg")
        self.assertTrue(p.is_file())
        self.assertEqual(p.name, "abc.jpg")

    def test_archive_prefix(self) -> None:
        p = sec.resolve_under_archive("archive/crops/abc.jpg")
        self.assertTrue(p.is_file())

    def test_traversal_rejected(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            sec.resolve_under_archive("../outside.txt")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_abs_under_archive(self) -> None:
        abs_p = self.root / "crops" / "abc.jpg"
        p = sec.resolve_under_archive(str(abs_p))
        self.assertEqual(p.resolve(), abs_p.resolve())


if __name__ == "__main__":
    unittest.main()
