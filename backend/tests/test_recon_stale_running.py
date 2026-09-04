"""Stale recon_scanner running recovery (dead worker thread)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from services import recon_scanner


class TestReconStaleRunning(unittest.TestCase):
    def tearDown(self) -> None:
        with recon_scanner._lock:
            recon_scanner._state.update(
                {
                    "status": "idle",
                    "job_id": None,
                    "message": "",
                    "phase": None,
                    "progress": 0.0,
                    "error": None,
                }
            )
            recon_scanner._thread = None

    def test_status_recovers_dead_thread(self) -> None:
        with recon_scanner._lock:
            recon_scanner._state["status"] = "running"
            recon_scanner._state["message"] = "stuck"
            recon_scanner._state["phase"] = "colmap"
            recon_scanner._thread = None
        st = recon_scanner.status()
        self.assertEqual(st["status"], "idle")
        self.assertIsNone(st.get("phase"))

    def test_colmap_running_false_after_recover(self) -> None:
        with recon_scanner._lock:
            recon_scanner._state["status"] = "running"
            recon_scanner._thread = None
        running = recon_scanner.status().get("status") == "running"
        self.assertFalse(running)


if __name__ == "__main__":
    unittest.main()
