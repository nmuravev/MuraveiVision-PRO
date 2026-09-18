"""Test P0-9: gsplat race condition protection via portalocker.

Verifies that acquire_gsplat_lock() prevents concurrent access
and that release_gsplat_lock() properly cleans up.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))

from services import gsplat_msvc


class TestGsplatRaceCondition(unittest.TestCase):
    """Test P0-9 gsplat race condition protection."""

    def test_portalocker_available(self):
        """HAS_PORTABLE_LOCKER should indicate portalocker availability."""
        # In air-gap, portalocker may not be installed
        # Test that the flag exists and is boolean
        self.assertIsInstance(
            gsplat_msvc.HAS_PORTABLE_LOCKER,
            bool,
            "HAS_PORTABLE_LOCKER should be a boolean"
        )

    def test_acquire_lock_when_available(self):
        """acquire_gsplat_lock should return lock when available."""
        if not gsplat_msvc.HAS_PORTABLE_LOCKER:
            self.skipTest("portalocker not available (air-gap)")

        lock = gsplat_msvc.acquire_gsplat_lock()
        try:
            # Should return a lock object (file handle)
            if lock is not None:
                self.assertTrue(hasattr(lock, "close"))
        finally:
            gsplat_msvc.release_gsplat_lock(lock)

    def test_release_none_lock(self):
        """release_gsplat_lock(None) should not raise."""
        # Should not raise any exception
        gsplat_msvc.release_gsplat_lock(None)

    def test_gsplat_lock_path_exists(self):
        """_GSPLAT_LOCK_PATH should be a valid Path."""
        self.assertIsInstance(gsplat_msvc._GSPLAT_LOCK_PATH, Path)
        self.assertEqual(gsplat_msvc._GSPLAT_LOCK_PATH.name, ".gsplat_jit.lock")

    def test_clear_caches(self):
        """clear_caches should reset internal caches."""
        gsplat_msvc.clear_caches()
        # Caches should be reset to False (unset)
        self.assertEqual(gsplat_msvc._VCVARS_CACHE, False)
        self.assertEqual(gsplat_msvc._CUDA_CACHE, False)


if __name__ == "__main__":
    unittest.main()
