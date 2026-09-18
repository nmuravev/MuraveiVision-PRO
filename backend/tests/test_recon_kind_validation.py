"""Test P1-5: kind validation in recon_export_artifact.

Verifies that only allowed artifact kinds (splat, dense, mesh, sparse)
are accepted, preventing probing attacks.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))

from api import recon


class TestReconKindValidation(unittest.TestCase):
    """Test P1-5 kind validation."""

    def test_valid_kinds_defined(self):
        """_VALID_RECON_KINDS should contain exactly 4 kinds."""
        expected = {"splat", "dense", "mesh", "sparse"}
        self.assertEqual(recon._VALID_RECON_KINDS, expected)

    def test_valid_kinds_is_frozenset(self):
        """_VALID_RECON_KINDS should be a frozenset (immutable)."""
        self.assertIsInstance(recon._VALID_RECON_KINDS, frozenset)

    def test_invalid_kind_rejected_by_logic(self):
        """Invalid kind should raise HTTPException in endpoint."""
        import asyncio
        from fastapi import HTTPException

        async def test():
            try:
                await recon.recon_export_artifact("test_job", "malicious_probe", {})
            except HTTPException as exc:
                return exc.status_code, exc.detail
            return None, None

        loop = asyncio.new_event_loop()
        try:
            status, detail = loop.run_until_complete(test())
            self.assertEqual(status, 400, "Should return 400 for invalid kind")
            self.assertIn("Invalid kind", detail)
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
