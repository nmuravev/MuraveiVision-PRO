"""Unit tests for SingleInstanceGuard (acquire + reject)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.single_instance import SingleInstanceGuard


class SingleInstanceTests(unittest.TestCase):
    """Tests for single-instance lock-file mechanism."""

    def setUp(self):
        """Clean up lock files before each test."""
        self.guard = SingleInstanceGuard()

    def tearDown(self):
        """Release lock and clean up after each test."""
        self.guard.release()

    def test_single_instance_acquire(self):
        """First instance should acquire lock successfully."""
        result = self.guard.acquire()
        self.assertTrue(result, "First instance should acquire lock")
        # Verify lock file exists in temp
        self.assertTrue(self.guard.lockfile_path.exists(), "Lock file should exist in temp")
        # Verify PID file exists
        self.assertTrue(self.guard.pidfile_path.exists(), "PID file should be written")

    def test_single_instance_reject(self):
        """Second instance should be rejected (lock already held)."""
        # First guard acquires
        self.assertTrue(self.guard.acquire())
        # Second guard tries to acquire same lock
        guard2 = SingleInstanceGuard()
        try:
            result = guard2.acquire()
            self.assertFalse(result, "Second instance should be rejected")
        finally:
            guard2.release()


if __name__ == '__main__':
    unittest.main()
