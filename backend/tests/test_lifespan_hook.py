"""R1: Unit tests for module-level _run_hook (non-fatal proof).

unittest.TestCase — pytest-style не соберётся (Ran 0 tests = ложный зелёный).
Гейт: "Ran 3 tests OK" (именно Ran 3, не 0).
"""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import _run_hook, failed_components


class RunHookTests(unittest.TestCase):
    """Tests for _run_hook non-fatal mechanism."""

    def setUp(self):
        """Clear failed_components before each test."""
        failed_components.clear()

    def test_sync_ok(self):
        """Sync fn returns OK → result returned, no failed_components."""
        result = asyncio.run(_run_hook("ok", lambda: "r"))
        self.assertEqual(result, "r")
        self.assertEqual(failed_components, [])

    def test_sync_raise(self):
        """Sync fn raises → None returned, name in failed_components."""
        def boom():
            raise ValueError("x")

        result = asyncio.run(_run_hook("boom", boom))
        self.assertIsNone(result)
        self.assertIn("boom", failed_components)

    def test_async_raise(self):
        """Async fn raises → None returned, name in failed_components."""
        async def boom():
            raise ValueError("y")

        result = asyncio.run(_run_hook("aboom", boom))
        self.assertIsNone(result)
        self.assertIn("aboom", failed_components)


if __name__ == "__main__":
    unittest.main()
