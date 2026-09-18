"""Test P1-7: WS undefined engine fix in detect.py.

Verifies that engine reference is safely accessible in error handler.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))

from api import detect


class TestWsEngineUndefined(unittest.TestCase):
    """Test P1-7 undefined engine in WS handler."""

    def test_engine_ref_variable_exists(self):
        """detect_ws should define _engine_ref for error handler."""
        import inspect
        source = inspect.getsource(detect.detect_ws)
        self.assertIn("_engine_ref", source, "_engine_ref should be defined")

    def test_engine_ref_used_in_error_handler(self):
        """_engine_ref should be used in error handler instead of engine."""
        import inspect
        source = inspect.getsource(detect.detect_ws)
        # Should use _engine_ref.mode not engine.mode in error handler
        self.assertIn("_engine_ref.mode", source, "_engine_ref.mode should be in error handler")


if __name__ == "__main__":
    unittest.main()
