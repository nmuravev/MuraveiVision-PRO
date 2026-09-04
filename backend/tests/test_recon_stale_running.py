"""Stale recon_scanner running recovery (dead worker thread)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import recon_scanner


class TestReconStaleRunning(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._root = Path(self._tmpdir.name)
        self._recon_patch = patch.object(recon_scanner, "RECON_ROOT", self._root)
        self._recon_patch.start()

    def tearDown(self) -> None:
        self._recon_patch.stop()
        self._tmpdir.cleanup()
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
            recon_scanner._state.pop("_reap_colmap_job", None)
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

    def test_recover_disk_terminal_while_thread_alive(self) -> None:
        class _Alive:
            def is_alive(self) -> bool:
                return True

        with recon_scanner._lock:
            recon_scanner._state["status"] = "running"
            recon_scanner._state["job_id"] = "deadjobdead01"
            recon_scanner._thread = _Alive()  # type: ignore[assignment]

        with patch.object(
            recon_scanner,
            "_read_manifest",
            return_value={"status": "error", "job_id": "deadjobdead01"},
        ), patch.object(recon_scanner, "terminate_colmap_for_job", return_value=0):
            with recon_scanner._lock:
                ok = recon_scanner._recover_stale_running_unlocked()
            self.assertTrue(ok)
            self.assertEqual(recon_scanner._state["status"], "idle")

    def test_force_release_allows_other_job_train(self) -> None:
        class _Alive:
            def is_alive(self) -> bool:
                return True

        with recon_scanner._lock:
            recon_scanner._state["status"] = "running"
            recon_scanner._state["job_id"] = "otherjob00001"
            recon_scanner._thread = _Alive()  # type: ignore[assignment]

        with patch.object(
            recon_scanner,
            "_read_manifest",
            return_value={"status": "error", "job_id": "otherjob00001"},
        ), patch.object(recon_scanner, "terminate_colmap_for_job", return_value=1) as kill:
            st = recon_scanner.force_release_for_train("315568ec29e4")
        self.assertNotEqual(st.get("status"), "running")
        kill.assert_called()

    def test_terminate_colmap_matches_job_path(self) -> None:
        class _FakeProc:
            def __init__(self, pid: int, name: str, cmdline: list[str]):
                self.info = {"pid": pid, "name": name, "cmdline": cmdline}
                self.pid = pid
                self._term = False

            def children(self, recursive: bool = False):
                return []

            def terminate(self) -> None:
                self._term = True

        job = "abcdef123456"
        needle = str((recon_scanner.RECON_ROOT / job / "colmap").resolve())
        target = _FakeProc(
            11,
            "colmap.exe",
            ["colmap", "mapper", "--database_path", needle + "\\database.db"],
        )
        other = _FakeProc(
            12,
            "colmap.exe",
            ["colmap", "mapper", "--database_path", "D:\\other\\colmap\\database.db"],
        )

        with patch("psutil.process_iter", return_value=[target, other]):
            n = recon_scanner.terminate_colmap_for_job(job)
        self.assertEqual(n, 1)
        self.assertTrue(target._term)
        self.assertFalse(other._term)

    def test_scrub_skips_alive_worker_job(self) -> None:
        class _Alive:
            def is_alive(self) -> bool:
                return True

        job = "aabbccddee01"
        job_dir = self._root / job
        job_dir.mkdir(parents=True)
        (job_dir / "manifest.json").write_text(
            '{"job_id":"aabbccddee01","status":"running"}',
            encoding="utf-8",
        )
        with recon_scanner._lock:
            recon_scanner._state["status"] = "idle"  # detached
            recon_scanner._state["job_id"] = job
            recon_scanner._thread = _Alive()  # type: ignore[assignment]
        recon_scanner._scrub_orphan_running_manifests()
        man = recon_scanner._read_manifest(job_dir)
        self.assertEqual(man.get("status"), "running")


if __name__ == "__main__":
    unittest.main()
