"""Unit tests for /ws/chat browser + peer relay."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import jwt
from fastapi.testclient import TestClient

from services import chat_ws
from services import db
from services import network as net
from services.db import get_jwt_secret
from services.security import JWT_ALG, TOKEN_TTL_SEC


def _token(role: str = "operator") -> str:
    payload = {
        "sub": role,
        "role": role,
        "exp": int(time.time()) + TOKEN_TTL_SEC,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALG)


class ChatWsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._orig_path = db.DB_PATH
        db.DB_PATH = Path(self._tmp.name)
        db._initialized = False
        db._jwt_secret_cache = None
        db.init_db()
        from main import app

        self.client = TestClient(app)

    def tearDown(self) -> None:
        db.DB_PATH = self._orig_path
        db._initialized = False
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def test_ws_rejects_missing_token(self) -> None:
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws/chat"):
                pass

    def test_ws_rejects_bad_token(self) -> None:
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws/chat?token=not-a-jwt"):
                pass

    def test_browser_receives_broadcast(self) -> None:
        tok = _token()
        with self.client.websocket_connect(f"/ws/chat?token={tok}") as ws:
            row = net.add_message(direction="out", sender="A", body="hi")
            asyncio.run(chat_ws.emit_chat_message(row))
            raw = ws.receive_text()
            data = json.loads(raw)
            self.assertEqual(data["type"], "chat.message")
            self.assertEqual(data["message"]["id"], row["id"])
            self.assertEqual(data["message"]["body"], "hi")

    def test_peer_rejected_when_not_server(self) -> None:
        net.save_config(mode="client", server_ip="127.0.0.1", port=8000, base_name="C")
        tok = _token()
        with self.assertRaises(Exception):
            with self.client.websocket_connect(f"/ws/chat?token={tok}&peer=1"):
                pass

    def test_peer_relay_and_dedup(self) -> None:
        net.save_config(mode="server", server_ip="127.0.0.1", port=8000, base_name="Hub")
        tok = _token()
        mid = "relay-id-1"
        with self.client.websocket_connect(f"/ws/chat?token={tok}&peer=1") as peer:
            peer.send_text(
                json.dumps(
                    {
                        "type": "peer.hello",
                        "base_id": "base-a",
                        "base_name": "База-A",
                    }
                )
            )
            peer.send_text(
                json.dumps(
                    {
                        "type": "chat.message",
                        "message": {
                            "id": mid,
                            "body": "peer says",
                            "sender": "База-A",
                            "created_at": time.time(),
                            "direction": "out",
                        },
                    }
                )
            )
            peer.send_text(
                json.dumps(
                    {
                        "type": "chat.message",
                        "message": {
                            "id": mid,
                            "body": "peer says again",
                            "sender": "База-A",
                            "created_at": time.time(),
                            "direction": "out",
                        },
                    }
                )
            )
        stored = net.get_message(mid)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["body"], "peer says")
        self.assertEqual(chat_ws.peer_count(), 0)


if __name__ == "__main__":
    unittest.main()
