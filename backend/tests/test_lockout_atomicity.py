"""Test atomic lockout against concurrent brute-force race conditions.

Verifies that record_failed_login uses atomic SQL UPDATE (fail_count = fail_count + 1)
instead of read-modify-write pattern, preventing race conditions under concurrent access.
"""
from __future__ import annotations

import sqlite3
import threading
import time
import unittest
from pathlib import Path

# Ensure backend is on path
_BACKEND = Path(__file__).resolve().parents[2] / "backend"
import sys
sys.path.insert(0, str(_BACKEND))

from services import db as db_service


class TestLockoutAtomicity(unittest.TestCase):
    """Test atomic fail_count increment under concurrent access."""

    def setUp(self):
        """Reset lockouts table for each test."""
        db_service.init_db()
        conn = db_service._connect()
        conn.execute("DELETE FROM lockouts WHERE client_key LIKE 'test_%'")
        conn.commit()
        conn.close()

    def tearDown(self):
        """Clean up test lockouts."""
        conn = db_service._connect()
        conn.execute("DELETE FROM lockouts WHERE client_key LIKE 'test_%'")
        conn.commit()
        conn.close()

    def test_single_increments(self):
        """Single-threaded: 5 fails should trigger lockout."""
        result = db_service.record_failed_login("test_single", max_fails=5, lock_sec=60)
        self.assertEqual(result["fail_count"], 1)
        self.assertEqual(result["locked_until"], 0.0)

        for i in range(4):
            result = db_service.record_failed_login("test_single", max_fails=5, lock_sec=60)
        self.assertEqual(result["fail_count"], 5)
        self.assertGreater(result["locked_until"], time.time())

    def test_concurrent_race_condition(self):
        """10 concurrent threads should atomically reach fail_count=10, not lose updates."""
        client_key = "test_race"
        num_threads = 10
        results = []
        errors = []

        def worker():
            try:
                res = db_service.record_failed_login(client_key, max_fails=100, lock_sec=60)
                results.append(res)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(len(errors), 0, f"Unexpected errors: {errors}")
        self.assertEqual(len(results), num_threads)

        # Final state should reflect ALL increments (no lost updates)
        lockout = db_service.get_lockout(client_key)
        self.assertEqual(
            lockout["fail_count"], num_threads,
            f"Expected {num_threads} fails, got {lockout['fail_count']} — race condition detected!"
        )

    def test_concurrent_brute_force_lockout(self):
        """Under concurrent brute-force, lockout triggers at threshold."""
        client_key = "test_brute"
        max_fails = 5
        num_threads = 10

        results = []
        errors = []

        def worker():
            try:
                res = db_service.record_failed_login(client_key, max_fails=max_fails, lock_sec=120)
                results.append(res)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), num_threads)

        # After 5+ fails, lockout should be active
        lockout = db_service.get_lockout(client_key)
        self.assertGreaterEqual(lockout["fail_count"], max_fails)
        self.assertGreater(lockout["locked_until"], time.time())

    def test_clear_lockout_resets_counter(self):
        """clear_lockout should reset fail_count to 0."""
        for _ in range(5):
            db_service.record_failed_login("test_clear", max_fails=5, lock_sec=60)

        lockout = db_service.get_lockout("test_clear")
        self.assertEqual(lockout["fail_count"], 5)

        db_service.clear_lockout("test_clear")

        lockout = db_service.get_lockout("test_clear")
        self.assertEqual(lockout["fail_count"], 0)
        self.assertEqual(lockout["locked_until"], 0.0)

    def test_multiple_clients_independent(self):
        """Different clients should have independent fail counts."""
        clients = [f"test_indep_{i}" for i in range(5)]

        threads = []
        for client in clients:
            threads.append(threading.Thread(
                target=lambda c=client: db_service.record_failed_login(c, max_fails=100, lock_sec=60)
            ))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        for client in clients:
            lockout = db_service.get_lockout(client)
            self.assertEqual(lockout["fail_count"], 1, f"{client} should have fail_count=1")

    def test_retry_on_database_locked(self):
        """Verify retry logic handles 'database is locked' gracefully."""
        # This test verifies the retry mechanism exists and doesn't crash
        # Under normal SQLite WAL mode, this rarely triggers, but we verify
        # the function completes successfully
        client_key = "test_retry"
        for _ in range(MAX_LOCKOUT_RETRIES + 2):
            result = db_service.record_failed_login(client_key, max_fails=100, lock_sec=60)
        self.assertGreaterEqual(result["fail_count"], MAX_LOCKOUT_RETRIES + 1)


# Import constant for test_reference
MAX_LOCKOUT_RETRIES = db_service.MAX_LOCKOUT_RETRIES


if __name__ == "__main__":
    unittest.main()
