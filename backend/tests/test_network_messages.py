"""Unit tests for network chat message replication (v3.2 MVP)."""
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


class NetworkMessageSyncTests(unittest.TestCase):
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

    def test_unsynced_and_mark(self) -> None:
        m = net.add_message(direction="out", sender="A", body="ping")
        pending = net.list_unsynced_out_messages()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], m["id"])
        self.assertIsNone(pending[0]["synced_at"])
        net.mark_message_synced(m["id"])
        self.assertEqual(net.list_unsynced_out_messages(), [])

    def test_upsert_newer_wins(self) -> None:
        net.upsert_message(message_id="m1", sender="B", body="v1", created_at=100)
        net.upsert_message(message_id="m1", sender="B", body="v2", created_at=200)
        row = net.get_message("m1")
        self.assertEqual(row["body"], "v2")
        net.upsert_message(message_id="m1", sender="B", body="stale", created_at=50)
        self.assertEqual(net.get_message("m1")["body"], "v2")
        self.assertEqual(net.get_message("m1")["direction"], "in")

    def test_add_message_idempotent(self) -> None:
        m = net.add_message(direction="out", sender="A", body="x", message_id="fixed-id")
        m2 = net.add_message(direction="out", sender="A", body="y", message_id="fixed-id")
        self.assertEqual(m["id"], m2["id"])
        self.assertEqual(net.get_message("fixed-id")["body"], "x")

    def test_unread_count(self) -> None:
        net.upsert_message(message_id="u1", sender="Peer", body="hi", created_at=1000)
        net.add_message(direction="out", sender="Me", body="out", created_at=1001)
        self.assertEqual(net.count_incoming_messages_since(999), 1)
        self.assertEqual(net.count_incoming_messages_since(1000), 0)

    def test_skip_self_on_pull(self) -> None:
        worker = NetworkSyncWorker()
        worker.base_id = "uuid-self"
        worker.base_name = "База-1"
        worker.hub_token = "tok"
        worker.hub_token_expires = time.time() + 3600
        now = time.time()
        payload = {
            "messages": [
                {
                    "id": "own-m",
                    "body": "mine",
                    "created_at": now,
                    "sender": "База-1",
                },
                {
                    "id": "peer-m",
                    "body": "hello",
                    "created_at": now + 1,
                    "sender": "База-2",
                },
            ]
        }

        async def _run() -> int:
            with mock.patch.object(
                worker,
                "_authed_request",
                new=mock.AsyncMock(return_value=_FakeResp(200, payload)),
            ):
                return await worker.pull_remote_messages()

        n = asyncio.run(_run())
        self.assertEqual(n, 1)
        self.assertIsNone(net.get_message("own-m"))
        peer = net.get_message("peer-m")
        self.assertIsNotNone(peer)
        self.assertEqual(peer["direction"], "in")
        self.assertEqual(peer["body"], "hello")

    def test_message_cursor_incremental(self) -> None:
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
                        "messages": [
                            {
                                "id": "r1",
                                "body": "a",
                                "created_at": t1,
                                "sender": "Other",
                            }
                        ]
                    },
                )
            return _FakeResp(200, {"messages": []})

        async def _run() -> None:
            with mock.patch.object(worker, "_authed_request", new=_req):
                await worker.pull_remote_messages()
                await worker.pull_remote_messages()

        asyncio.run(_run())
        self.assertEqual(calls[0], 0.0)
        self.assertAlmostEqual(calls[1], t1, places=3)
        self.assertAlmostEqual(worker.message_cursor or 0, t1, places=3)

    def test_push_marks_synced(self) -> None:
        net.save_config(mode="client", server_ip="127.0.0.1", port=8000, base_name="База-2")
        m = net.add_message(direction="out", sender="База-2", body="outbox")
        worker = NetworkSyncWorker()
        worker.base_id = net.ensure_base_id()
        worker.base_name = "База-2"
        worker.hub_token = "tok"
        worker.hub_token_expires = time.time() + 3600

        async def _run() -> int:
            with mock.patch.object(
                worker,
                "_authed_request",
                new=mock.AsyncMock(return_value=_FakeResp(200, {"ok": True})),
            ):
                return await worker.push_local_messages()

        n = asyncio.run(_run())
        self.assertEqual(n, 1)
        self.assertEqual(net.list_unsynced_out_messages(), [])
        self.assertIsNotNone(net.get_message(m["id"])["synced_at"])

    def test_dup_out_not_upserted_as_in(self) -> None:
        """Local out row with same id must not flip to in on pull."""
        mid = "dup-1"
        net.add_message(direction="out", sender="Me", body="mine", message_id=mid)
        worker = NetworkSyncWorker()
        worker.base_id = "me-id"
        worker.base_name = "OtherName"
        worker.hub_token = "tok"
        worker.hub_token_expires = time.time() + 3600
        payload = {
            "messages": [
                {
                    "id": mid,
                    "body": "mine",
                    "created_at": time.time(),
                    "sender": "HubCopy",
                }
            ]
        }

        async def _run() -> int:
            with mock.patch.object(
                worker,
                "_authed_request",
                new=mock.AsyncMock(return_value=_FakeResp(200, payload)),
            ):
                return await worker.pull_remote_messages()

        n = asyncio.run(_run())
        self.assertEqual(n, 0)
        self.assertEqual(net.get_message(mid)["direction"], "out")

    def test_resolve_lan_ipv4_env_override(self) -> None:
        with mock.patch.dict(os.environ, {"MURAVEI_NETWORK_ADVERTISE_IP": "10.9.8.7"}):
            self.assertEqual(net.resolve_lan_ipv4(), "10.9.8.7")

    def test_heartbeat_uses_resolve_lan(self) -> None:
        worker = NetworkSyncWorker()
        worker.base_id = "b1"
        worker.base_name = "База"
        worker.hub_token = "tok"
        worker.hub_token_expires = time.time() + 3600
        seen: dict = {}

        async def _req(method, path, **kwargs):
            seen["json"] = kwargs.get("json")
            return _FakeResp(200, {"ok": True})

        async def _run() -> None:
            with mock.patch.object(net, "resolve_lan_ipv4", return_value="192.0.2.55"):
                with mock.patch.object(worker, "_authed_request", new=_req):
                    await worker.send_heartbeat()

        asyncio.run(_run())
        self.assertEqual(seen["json"]["ip"], "192.0.2.55")
        self.assertEqual(worker.advertise_ip, "192.0.2.55")


if __name__ == "__main__":
    unittest.main()
