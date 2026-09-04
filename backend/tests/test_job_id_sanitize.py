"""Unit tests for job_id sanitization (no production archive IDs)."""
from __future__ import annotations

import io
import unittest
from pathlib import Path

from services.job_ids import join_job_id_tokens, sanitize_job_dir, sanitize_job_id


class JobIdSanitizeTests(unittest.TestCase):
    def test_strips_spaces_and_newlines(self) -> None:
        buf = io.StringIO()
        # Synthetic 12-hex with wrap/space — not a real archive job.
        raw = "abcd\nef12 3456"
        cleaned = sanitize_job_id(raw, stream=buf)
        self.assertEqual(cleaned, "abcdef123456")
        self.assertIn("sanitized", buf.getvalue())

    def test_warns_on_non_hex12(self) -> None:
        buf = io.StringIO()
        cleaned = sanitize_job_id("short", stream=buf)
        self.assertEqual(cleaned, "short")
        self.assertIn("may be invalid", buf.getvalue())

    def test_join_tokens_nargs(self) -> None:
        buf = io.StringIO()
        # Simulate argparse nargs='+' split of a wrapped id.
        joined = join_job_id_tokens(["ab", "cd", "ef123456"])
        # re-run with stream via sanitize only
        cleaned = sanitize_job_id("ab cd ef123456", stream=buf)
        self.assertEqual(joined, "abcdef123456")
        self.assertEqual(cleaned, "abcdef123456")

    def test_join_none(self) -> None:
        self.assertIsNone(join_job_id_tokens(None))

    def test_sanitize_job_dir_leaf(self) -> None:
        buf = io.StringIO()
        p = Path("/tmp/archive/recon") / "ab cd ef123456"
        # Force warn through sanitize_job_id path
        out = sanitize_job_dir(p, warn=True)
        # Parent preserved, leaf cleaned
        self.assertEqual(out.name, "abcdef123456")
        self.assertEqual(out.parent, p.parent)


if __name__ == "__main__":
    unittest.main()
