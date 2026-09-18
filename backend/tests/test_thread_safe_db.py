"""Test P1-2: Thread-safe DB operations.

Verifies that concurrent write operations are protected by _write_lock
and don't cause data corruption or OperationalError.
"""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))

from services import db


class TestThreadSafeDb(unittest.TestCase):
    """Test P1-2 thread-safe DB operations."""

    def setUp(self):
        """Save original state."""
        self._orig_write_lock = db._write_lock
        self._orig_initialized = db._initialized
        db._initialized = False  # Force re-init

    def tearDown(self):
        """Restore original state."""
        db._initialized = self._orig_initialized

    def test_write_lock_exists(self):
        """_write_lock should be a threading.Lock."""
        self.assertIsInstance(db._write_lock, type(threading.Lock()))

    def test_concurrent_settings_writes(self):
        """Concurrent set_setting should not raise."""
        errors = []

        def writer(n):
            try:
                for i in range(20):
                    db.set_setting(f"key_{n}_{i}", f"value_{n}_{i}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(len(errors), 0, f"Errors during concurrent writes: {errors[:3]}")

    def test_concurrent_lockout_writes(self):
        """Concurrent record_failed_login should not raise."""
        errors = []

        def writer(n):
            try:
                for i in range(20):
                    db.record_failed_login(f"client_{n}", max_fails=100, lock_sec=60)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(len(errors), 0, f"Errors during concurrent lockouts: {errors[:3]}")

    def test_concurrent_pin_updates(self):
        """Concurrent update_pin should not raise."""
        errors = []

        def writer(n):
            try:
                for i in range(10):
                    db.update_pin("operator", f"123456{i % 10}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(len(errors), 0, f"Errors during concurrent pin updates: {errors[:3]}")


if __name__ == "__main__":
    unittest.main()
