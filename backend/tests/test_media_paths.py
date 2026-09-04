"""Path canonicalization for media / detections (archive-relative keys)."""
from __future__ import annotations

import unittest
from pathlib import Path

from services.db import normalize_media_path
from services.security import archive_root

class TestNormalizeMediaPath(unittest.TestCase):
    def test_windows_absolute(self) -> None:
        self.assertEqual(
            normalize_media_path(r"D:\LLM\MuraveiVision-PRO\archive\video_2026.mp4"),
            "video_2026.mp4",
        )

    def test_windows_forward_slashes(self) -> None:
        self.assertEqual(
            normalize_media_path("D:/LLM/MuraveiVision-PRO/archive/clips/a.mp4"),
            "clips/a.mp4",
        )

    def test_unix_absolute(self) -> None:
        self.assertEqual(
            normalize_media_path("/home/user/project/archive/video.mp4"),
            "video.mp4",
        )

    def test_archive_prefix(self) -> None:
        self.assertEqual(normalize_media_path("archive/video.mp4"), "video.mp4")
        self.assertEqual(normalize_media_path("archive/subdir/x.mp4"), "subdir/x.mp4")

    def test_bare_name(self) -> None:
        self.assertEqual(normalize_media_path("video.mp4"), "video.mp4")

    def test_mixed_slashes(self) -> None:
        self.assertEqual(
            normalize_media_path(r"D:/LLM\MuraveiVision-PRO\archive\sub\v.mp4"),
            "sub/v.mp4",
        )

    def test_empty(self) -> None:
        self.assertEqual(normalize_media_path(""), "")
        self.assertEqual(normalize_media_path(None), "")  # type: ignore[arg-type]


class TestClientArchivePath(unittest.TestCase):
    def test_relative_to_archive_root(self) -> None:
        from api.media import _client_archive_path

        root = archive_root()
        sample = root / "clips" / "demo.mp4"
        self.assertEqual(_client_archive_path(sample), "archive/clips/demo.mp4")

    def test_archive_root_itself(self) -> None:
        from api.media import _client_archive_path

        self.assertEqual(_client_archive_path(archive_root()), "archive")

    def test_no_hardcoded_drive(self) -> None:
        from api.media import _client_archive_path

        root = archive_root()
        p = root / "x.mp4"
        out = _client_archive_path(p)
        self.assertTrue(out.startswith("archive/"))
        self.assertNotIn(":\\", out)
        self.assertFalse(Path(out).is_absolute())


class TestToArchiveMediaPathMirror(unittest.TestCase):
    """Mirror FE toArchiveMediaPath rules for the cases normalize already covers."""

    def test_fe_canonical_matches_db_key(self) -> None:
        samples = [
            r"D:\LLM\proj\archive\video.mp4",
            "archive/video.mp4",
            "video.mp4",
            "/data/archive/nested/a.mp4",
        ]
        for s in samples:
            key = normalize_media_path(s)
            # FE would pass archive/{key} into Viewer; DB key stays without prefix
            self.assertFalse(key.lower().startswith("archive/"))
            self.assertNotIn("\\", key)


if __name__ == "__main__":
    unittest.main()
