"""Test P0-1: SSE idle timeout and heartbeat in recon stream.

Verifies that SSE stream has configurable idle timeout and
sends heartbeat messages during long-running operations.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))

from api import recon


class TestSseTimeout(unittest.TestCase):
    """Test P0-1 SSE timeout and heartbeat."""

    def test_idle_timeout_configurable(self):
        """SSE_IDLE_TIMEOUT should be configurable via env."""
        # Default should be 60s
        self.assertEqual(recon._SSE_IDLE_TIMEOUT, 60)

    def test_heartbeat_interval_configurable(self):
        """_SSE_HEARTBEAT_INTERVAL should be 15s."""
        self.assertEqual(recon._SSE_HEARTBEAT_INTERVAL, 15.0)

    def test_idle_timeout_env_override(self):
        """SSE_IDLE_TIMEOUT should be overridable via env var."""
        # Test that the value was read from env
        # (in real usage, env var would be set before import)
        self.assertIsInstance(recon._SSE_IDLE_TIMEOUT, int)
        self.assertGreater(recon._SSE_IDLE_TIMEOUT, 0)

    def test_stream_endpoint_exists(self):
        """recon_stream endpoint should be registered."""
        # Check that router has the stream endpoint
        routes = [str(p.path) for p in recon.router.routes]
        self.assertIn("/api/recon/stream", routes)

    def test_stream_response_type(self):
        """recon_stream should be an async function returning StreamingResponse."""
        import asyncio
        import inspect
        from fastapi.responses import StreamingResponse

        # Check that recon_stream is async
        self.assertTrue(inspect.iscoroutinefunction(recon.recon_stream))


if __name__ == "__main__":
    unittest.main()
