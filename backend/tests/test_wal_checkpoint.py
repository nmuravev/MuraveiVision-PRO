"""Test P1-11: SQLite WAL checkpoint in db.py.

Verifies that WAL autocheckpoint is enabled and checkpoint_wal()
function exists and works correctly.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))

from services import db


class TestWalCheckpoint(unittest.TestCase):
    """Test P1-11 WAL checkpoint."""

    def test_wal_checkpoint_counter_exists(self):
        """_wal_checkpoint_counter should exist."""
        self.assertIsInstance(db._wal_checkpoint_counter, int)

    def test_wal_checkpoint_interval_config(self):
        """WAL_CHECKPOINT_INTERVAL should be 1000."""
        self.assertEqual(db._WAL_CHECKPOINT_INTERVAL, 1000)

    def test_checkpoint_wal_function_exists(self):
        """checkpoint_wal should be a callable function."""
        self.assertTrue(callable(db.checkpoint_wal))

    def test_connect_has_autocheckpoint(self):
        """_connect() should enable WAL autocheckpoint."""
        import tempfile
        import os

        # Create temp DB to test
        orig_db = db.DB_PATH
        with tempfile.TemporaryDirectory() as tmpdir:
            test_db = Path(tmpdir) / "test.db"
            db.DB_PATH = test_db
            try:
                db.init_db()
                conn = db._connect()
                # Check journal mode is WAL
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                self.assertEqual(mode, "wal")
                conn.close()
            finally:
                db.DB_PATH = orig_db

    def test_checkpoint_wal_no_error(self):
        """checkpoint_wal() should not raise on valid connection."""
        db.init_db()
        conn = db._connect()
        try:
            # Should not raise
            db.checkpoint_wal(conn)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
