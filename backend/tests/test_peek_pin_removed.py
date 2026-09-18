"""Test P1-1: /peek-pin endpoint removed.

Verifies that the plaintext PIN exposure endpoint has been removed
and CLI script exists as replacement.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))

from api import auth


class TestPeekPinRemoved(unittest.TestCase):
    """Test P1-1 /peek-pin removal."""

    def test_peek_pin_endpoint_removed(self):
        """/peek-pin endpoint should NOT be in router routes."""
        routes = [str(p.path) for p in auth.router.routes]
        peek_routes = [r for r in routes if "peek" in r.lower()]
        self.assertEqual(
            len(peek_routes), 0,
            f"/peek-pin endpoint still exists: {peek_routes}"
        )

    def test_peek_roles_constant_removed(self):
        """PEEK_ROLES constant should be removed from auth module."""
        self.assertFalse(hasattr(auth, "PEEK_ROLES"), "PEEK_ROLES should be removed")

    def test_pin_from_b64_import_removed(self):
        """pin_from_b64 should not be imported in auth module."""
        # Check that auth module doesn't import pin_from_b64
        import inspect
        source = inspect.getsource(auth)
        self.assertNotIn(
            "pin_from_b64", source,
            "pin_from_b64 import should be removed"
        )

    def test_reset_pin_script_exists(self):
        """reset_pin.py CLI script should exist."""
        script_path = _BACKEND / "scripts" / "reset_pin.py"
        self.assertTrue(script_path.is_file(), "reset_pin.py should exist")


if __name__ == "__main__":
    unittest.main()
