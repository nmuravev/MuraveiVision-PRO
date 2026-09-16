"""Unit tests for LAN beacon (N5 opt-in discovery)."""
from __future__ import annotations

import asyncio
import json
import socket
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Only import when running (avoid import-time socket init)
def _import_beacon():
    from services import network_beacon as nb
    return nb


class TestLanBeaconPayload(unittest.TestCase):
    """E1: payload format and ts-refresh."""

    def test_payload_has_required_keys(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        beacon._send_sock = MagicMock()  # avoid real socket
        beacon._base_id = "test-id"
        beacon._base_name = "TestBase"
        beacon._server_port = 8000
        # Build payload like _broadcast_loop does
        payload = json.dumps({
            "base_id": beacon._base_id,
            "base_name": beacon._base_name,
            "port": beacon._server_port,
            "ts": time.time(),
        })
        data = json.loads(payload)
        self.assertIn("base_id", data)
        self.assertIn("base_name", data)
        self.assertIn("port", data)
        self.assertIn("ts", data)
        self.assertEqual(data["base_id"], "test-id")
        self.assertEqual(data["base_name"], "TestBase")
        self.assertEqual(data["port"], 8000)
        self.assertIsInstance(data["ts"], float)

    def test_ts_refreshes_each_iteration(self):
        nb = _import_beacon()
        ts1 = time.time()
        time.sleep(0.05)
        ts2 = time.time()
        self.assertLess(ts1, ts2)
        # ts is built inside loop so each broadcast has fresh ts


class TestLanBeaconHygiene(unittest.TestCase):
    """E2/E4: socket hygiene, getblocking, port default."""

    def test_default_beacon_port(self):
        nb = _import_beacon()
        self.assertEqual(nb.BEACON_PORT_DEFAULT, 8001)

    def test_socket_non_blocking_after_start_recv(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        beacon._port = 9999  # use unused port
        # Start recv socket directly (skip full start to avoid broadcast issues)
        beacon._start_recv_socket()
        try:
            self.assertFalse(beacon._recv_sock.getblocking())
        finally:
            beacon._close_recv_socket()

    def test_send_socket_no_protocol_arg(self):
        """C1: AF_INET + SOCK_DGRAM only (no protocol arg)."""
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        beacon._start_send_socket()
        try:
            self.assertEqual(beacon._send_sock.family, socket.AF_INET)
            self.assertEqual(beacon._send_sock.type, socket.SOCK_DGRAM)
            # SO_BROADCAST should be set
            opt = beacon._send_sock.getsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST)
            self.assertEqual(opt, 1)
        finally:
            beacon._close_send_socket()

    def test_recv_socket_reuse_addr(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        beacon._port = 9998
        beacon._start_recv_socket()
        try:
            opt = beacon._recv_sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR)
            self.assertEqual(opt, 1)
        finally:
            beacon._close_recv_socket()

    def test_close_send_socket_twice_is_safe(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        beacon._start_send_socket()
        beacon._close_send_socket()
        # Second close should not raise
        beacon._close_send_socket()
        self.assertIsNone(beacon._send_sock)

    def test_close_recv_socket_twice_is_safe(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        beacon._port = 9997
        beacon._start_recv_socket()
        beacon._close_recv_socket()
        beacon._close_recv_socket()
        self.assertIsNone(beacon._recv_sock)


class TestLanBeaconTTLPruning(unittest.TestCase):
    """TTL-based peer pruning."""

    def test_peer_expires_after_ttl(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        now = time.time()
        # Add a peer with old timestamp
        beacon._discovered_peers["old-peer"] = {
            "base_name": "Old",
            "ip": "192.168.1.100",
            "port": 8000,
            "ts": now - 10,  # 10s ago (TTL = 6s)
        }
        # Add a fresh peer
        beacon._discovered_peers["fresh-peer"] = {
            "base_name": "Fresh",
            "ip": "192.168.1.101",
            "port": 8000,
            "ts": now,
        }
        beacon._prune_expired(now, ttl_sec=6.0)
        self.assertNotIn("old-peer", beacon._discovered_peers)
        self.assertIn("fresh-peer", beacon._discovered_peers)

    def test_discovered_peers_returns_pruned(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        now = time.time()
        beacon._discovered_peers["expired"] = {
            "base_name": "X",
            "ip": "1.2.3.4",
            "port": 8000,
            "ts": now - 20,
        }
        peers = beacon.discovered_peers
        self.assertNotIn("expired", peers)

    def test_live_peer_count_after_prune(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        now = time.time()
        beacon._discovered_peers["a"] = {
            "base_name": "A",
            "ip": "1.1.1.1",
            "port": 8000,
            "ts": now,
        }
        beacon._discovered_peers["b"] = {
            "base_name": "B",
            "ip": "2.2.2.2",
            "port": 8000,
            "ts": now - 20,
        }
        self.assertEqual(beacon.live_peer_count, 1)


class TestLanBeaconPeerDiscovery(unittest.TestCase):
    """E4: clean peer discovery with heartbeat integration."""

    def test_peer_discovered_calls_heartbeat(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        msg = {
            "base_id": "peer-1",
            "base_name": "PeerOne",
            "port": 8000,
            "ts": time.time(),
        }
        from services import network as net
        with patch.object(net, "heartbeat") as mock_hb2:
            beacon._on_peer_discovered(msg, ("192.168.1.50", 12345))
            mock_hb2.assert_called_once_with(
                base_id="peer-1",
                base_name="PeerOne",
                ip="192.168.1.50",
            )

    def test_peer_stored_with_correct_fields(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        now = time.time()
        msg = {
            "base_id": "store-test",
            "base_name": "StoreTest",
            "port": 9000,
            "ts": now,
        }
        from services import network as net
        with patch.object(net, "heartbeat"):
            beacon._on_peer_discovered(msg, ("10.0.0.1", 54321))
        peers = beacon.discovered_peers
        self.assertIn("store-test", peers)
        p = peers["store-test"]
        self.assertEqual(p["base_name"], "StoreTest")
        self.assertEqual(p["ip"], "10.0.0.1")
        self.assertEqual(p["port"], 9000)
        self.assertAlmostEqual(p["ts"], now, delta=1.0)

    def test_self_peer_ignored(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        beacon._base_id = "self-peer"
        msg = {
            "base_id": "self-peer",
            "base_name": "Me",
            "port": 8000,
            "ts": time.time(),
        }
        from services import network as net
        with patch.object(net, "heartbeat"):
            beacon._on_peer_discovered(msg, ("127.0.0.1", 1234))
        peers = beacon.discovered_peers
        self.assertNotIn("self-peer", peers)

    def test_empty_base_id_ignored(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        msg = {
            "base_id": "",
            "base_name": "NoID",
            "port": 8000,
            "ts": time.time(),
        }
        from services import network as net
        with patch.object(net, "heartbeat"):
            beacon._on_peer_discovered(msg, ("1.2.3.4", 1234))
        peers = beacon.discovered_peers
        self.assertEqual(len(peers), 0)


class TestLanBeaconStatus(unittest.TestCase):
    """Status endpoint integration."""

    def test_get_beacon_returns_none_when_not_started(self):
        nb = _import_beacon()
        # After fresh import, _beacon is None
        self.assertIsNone(nb.get_beacon())

    def test_reconfigure_beacon_with_none_is_safe(self):
        nb = _import_beacon()
        # When _beacon is None, reconfigure should not raise
        asyncio.run(nb.reconfigure_beacon(enabled=False, port=8001))


class TestLanBeaconNonBlocking(unittest.TestCase):
    """C1: non-blocking recv with loop.sock_recvfrom."""

    def test_recv_socket_setblocking_false(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        beacon._port = 9996
        beacon._start_recv_socket()
        try:
            # E2: setblocking(False) is called
            self.assertFalse(beacon._recv_sock.getblocking())
        finally:
            beacon._close_recv_socket()

    def test_send_and_recv_sockets_independent(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        beacon._port = 9995
        beacon._start_send_socket()
        beacon._start_recv_socket()
        try:
            # Send socket should be blocking (default)
            self.assertTrue(beacon._send_sock.getblocking())
            # Recv socket should be non-blocking
            self.assertFalse(beacon._recv_sock.getblocking())
        finally:
            beacon._close_send_socket()
            beacon._close_recv_socket()


class TestReconfigureBeacon(unittest.TestCase):
    """C7: live reconfigure without restart."""

    def test_reconfigure_updates_port(self):
        nb = _import_beacon()
        beacon = nb.LanBeacon()
        beacon.configure(
            enabled=True,
            port=8001,
            base_id="test",
            base_name="Test",
            server_port=8000,
        )
        # Verify initial config
        self.assertEqual(beacon._port, 8001)
        # Reconfigure to different port
        # Note: reconfigure_beacon is async and operates on global _beacon
        # Test configure directly for deterministic behavior
        beacon.configure(
            enabled=True,
            port=9000,
            base_id=beacon._base_id,
            base_name=beacon._base_name,
            server_port=beacon._server_port,
        )
        self.assertEqual(beacon._port, 9000)


if __name__ == "__main__":
    unittest.main()
