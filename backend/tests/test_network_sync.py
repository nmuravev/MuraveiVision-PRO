"""Unit tests for network replication 3.1 (upsert, skip-self, no demo mirror, worker)."""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from services import db
from services import network as net
from services.network_sync import NetworkSyncWorker


class _FakeResp:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload


class NetworkSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._orig_path = db.DB_PATH
        self._orig_init = db._initialized
        self._orig_jwt = db._jwt_secret_cache
        db.DB_PATH = Path(self._tmp.name)
        db._initialized = False
        db._jwt_secret_cache = None
        db.init_db()

    def tearDown(self) -> None:
        db.DB_PATH = self._orig_path
        db._initialized = False
        db._jwt_secret_cache = self._orig_jwt
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def test_upsert_newer_wins(self) -> None:
        net.upsert_target(target_id="test-1", class_name="old", created_at=100, notes="v1")
        net.upsert_target(target_id="test-1", class_name="new", created_at=200, notes="v2")
        row = net.get_target("test-1")
        self.assertEqual(row["class_name"], "new")
        self.assertEqual(float(row["created_at"]), 200.0)
        net.upsert_target(target_id="test-1", class_name="stale", created_at=50, notes="v0")
        row = net.get_target("test-1")
        self.assertEqual(row["class_name"], "new")
        self.assertEqual(row["notes"], "v2")
        self.assertEqual(row["direction"], "in")
        self.assertIsNone(row["synced_at"])

    def test_skip_own_targets(self) -> None:
        worker = NetworkSyncWorker()
        worker.base_id = "uuid-self"
        worker.base_name = "База-1"
        self.assertTrue(worker._is_self_source("uuid-self"))
        self.assertTrue(worker._is_self_source("База-1"))
        self.assertFalse(worker._is_self_source("База-2"))

        now = time.time()
        payload = {
            "targets": [
                {
                    "id": "own-1",
                    "class_name": "tank",
                    "created_at": now,
                    "source_base": "База-1",
                },
                {
                    "id": "peer-1",
                    "class_name": "truck",
                    "created_at": now + 1,
                    "source_base": "База-2",
                    "confidence": 0.9,
                },
            ]
        }

        async def _run() -> int:
            worker.hub_token = "tok"
            worker.hub_token_expires = time.time() + 3600
            with mock.patch.object(
                worker,
                "_authed_request",
                new=mock.AsyncMock(return_value=_FakeResp(200, payload)),
            ):
                return await worker.pull_remote_targets()

        n = asyncio.run(_run())
        self.assertEqual(n, 1)
        self.assertIsNone(net.get_target("own-1"))
        peer = net.get_target("peer-1")
        self.assertIsNotNone(peer)
        self.assertEqual(peer["direction"], "in")
        self.assertEqual(peer["class_name"], "truck")
        self.assertAlmostEqual(worker.cursor or 0, now + 1, places=3)

    def test_demo_mirror_gone(self) -> None:
        from api.network import TargetBody, post_target

        net.save_config(mode="server", server_ip="127.0.0.1", port=8000, base_name="База-1")
        body = TargetBody(class_name="tank", confidence=0.8, source_video="clip.mp4")

        async def _post() -> dict:
            return await post_target(body, user={"role": "operator"})

        result = asyncio.run(_post())
        tid = result["target"]["id"]
        conn = db._connect()
        try:
            rows = conn.execute(
                "SELECT direction FROM network_targets WHERE id = ?", (tid,)
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual([r[0] for r in rows], ["out"])

    def test_worker_graceful_degradation(self) -> None:
        net.save_config(
            mode="client",
            server_ip="127.0.0.1",
            port=8000,
            base_name="База-2",
            hub_pin="1234567",
        )
        worker = NetworkSyncWorker()
        worker.base_id = net.ensure_base_id()

        async def _boom(*_a, **_k):
            raise ConnectionError("hub down")

        with mock.patch.object(worker, "login_to_hub", new=mock.AsyncMock(side_effect=_boom)):
            asyncio.run(worker.sync_tick())
        self.assertIsNotNone(worker.last_error)
        self.assertIn("hub down", worker.last_error)

    def test_cursor_incremental(self) -> None:
        worker = NetworkSyncWorker()
        worker.base_id = "self"
        worker.base_name = "Me"
        worker.hub_token = "tok"
        worker.hub_token_expires = time.time() + 3600
        t1 = time.time()
        calls: list[float] = []

        async def _req(method, path, **kwargs):
            params = kwargs.get("params") or {}
            calls.append(float(params.get("since", -1)))
            if len(calls) == 1:
                return _FakeResp(
                    200,
                    {
                        "targets": [
                            {
                                "id": "r1",
                                "class_name": "tank",
                                "created_at": t1,
                                "source_base": "Other",
                            }
                        ]
                    },
                )
            return _FakeResp(200, {"targets": []})

        async def _run() -> None:
            with mock.patch.object(worker, "_authed_request", new=_req):
                await worker.pull_remote_targets()
                await worker.pull_remote_targets()

        asyncio.run(_run())
        self.assertEqual(calls[0], 0.0)
        self.assertAlmostEqual(calls[1], t1, places=3)
        self.assertAlmostEqual(worker.cursor or 0, t1, places=3)

    def test_unsynced_null_synced_at(self) -> None:
        net.save_config(mode="server", server_ip="127.0.0.1", port=8000, base_name="База-1")
        row = net.add_target(direction="out", class_name="jeep")
        pending = net.list_unsynced_out_targets()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], row["id"])
        self.assertIsNone(pending[0]["synced_at"])
        net.mark_target_synced(row["id"])
        self.assertEqual(net.list_unsynced_out_targets(), [])


if __name__ == "__main__":
    unittest.main()
