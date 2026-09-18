"""Test path traversal protection in recon_scanner.asset_path.

Verifies that asset_path() rejects paths containing '..' sequences
that would escape the job directory.
"""
from __future__ import annotations

import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
import sys
sys.path.insert(0, str(_BACKEND))

from services import recon_scanner


class TestAssetPathTraversal(unittest.TestCase):
    """Test path traversal protection in asset_path()."""

    def setUp(self):
        """Create a temporary job directory for testing."""
        import tempfile
        self.tmpdir = Path(tempfile.mkdtemp())
        # Override RECON_ROOT temporarily
        self._original_recon_root = recon_scanner.RECON_ROOT
        recon_scanner.RECON_ROOT = self.tmpdir

    def tearDown(self):
        """Clean up temporary directory."""
        recon_scanner.RECON_ROOT = self._original_recon_root
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_normal_asset_returns_path(self):
        """Normal asset within job directory should work."""
        job_id = "test_normal_job"
        job_dir = self.tmpdir / job_id
        job_dir.mkdir()
        asset_file = job_dir / "model.ply"
        asset_file.write_bytes(b"fake ply data")

        path = recon_scanner.asset_path(job_id, "model.ply")
        self.assertEqual(path, asset_file.resolve())

    def test_path_traversal_dotdot_rejected(self):
        """Path traversal with '..' should raise ValueError."""
        job_id = "test_traversal_job"
        job_dir = self.tmpdir / job_id
        job_dir.mkdir()

        # Create a file outside job dir to tempt traversal
        escape_file = self.tmpdir / "escape.txt"
        escape_file.write_bytes(b"secret")

        with self.assertRaises(ValueError) as ctx:
            recon_scanner.asset_path(job_id, "../../../escape.txt")

        self.assertIn("Path traversal", str(ctx.exception))

    def test_path_traversal_absolute_rejected(self):
        """Absolute path should be rejected."""
        job_id = "test_abs_job"
        job_dir = self.tmpdir / job_id
        job_dir.mkdir()

        with self.assertRaises(ValueError):
            recon_scanner.asset_path(job_id, "/etc/passwd")

    def test_path_traversal_mixed_rejected(self):
        """Mixed path with '..' embedded should be rejected."""
        job_id = "test_mixed_job"
        job_dir = self.tmpdir / job_id
        job_dir.mkdir()

        with self.assertRaises(ValueError):
            recon_scanner.asset_path(job_id, "subdir/../../escape.txt")

    def test_nonexistent_file_rejected(self):
        """Nonexistent file within job dir should raise FileNotFoundError."""
        job_id = "test_missing_job"
        job_dir = self.tmpdir / job_id
        job_dir.mkdir()

        with self.assertRaises(FileNotFoundError):
            recon_scanner.asset_path(job_id, "nonexistent.ply")


if __name__ == "__main__":
    unittest.main()
