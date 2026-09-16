"""Opt-in LAN UDP beacon: broadcast + discovery (async-safe)."""
from __future__ import annotations

import asyncio
import json
import socket
import time
from typing import Any

BEACON_PORT_DEFAULT = 8001
BEACON_INTERVAL = 2.0  # seconds
BROADCAST_ADDR = "255.255.255.255"
TTL_MULTIPLIER = 3  # prune peers older than 3×interval


class LanBeacon:
    """Non-blocking UDP beacon with TTL-based peer pruning."""

    def __init__(self) -> None:
        self._enabled = False
        self._port = BEACON_PORT_DEFAULT
        self._base_id = ""
        self._base_name = ""
        self._server_port = 8000
        self._running = False
        self._broadcast_task: asyncio.Task | None = None
        self._recv_task: asyncio.Task | None = None
        # C2: sockets as instance attributes
        self._send_sock: socket.socket | None = None
        self._recv_sock: socket.socket | None = None
        # discovered peers: base_id -> {base_name, ip, port, ts}
        self._discovered_peers: dict[str, dict[str, Any]] = {}

    def configure(
        self,
        enabled: bool,
        port: int,
        base_id: str,
        base_name: str,
        server_port: int,
    ) -> None:
        self._enabled = enabled
        self._port = port
        self._base_id = base_id
        self._base_name = base_name
        self._server_port = server_port

    async def start(self) -> None:
        """Start broadcast + recv sockets if enabled."""
        if not self._enabled:
            await self.stop()
            return
        await self.stop()  # clean previous sockets
        self._running = True
        self._start_send_socket()
        self._start_recv_socket()
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def stop(self) -> None:
        """Cancel tasks and close sockets. C2: no fd leak."""
        self._running = False
        for task in (self._broadcast_task, self._recv_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._close_send_socket()
        self._close_recv_socket()

    # ── send socket ──────────────────────────────────────────
    def _start_send_socket(self) -> None:
        """C1: AF_INET + SOCK_DGRAM only (no third arg = protocol)."""
        if self._send_sock is not None:
            return
        self._send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def _close_send_socket(self) -> None:
        if self._send_sock is not None:
            self._send_sock.close()
            self._send_sock = None

    async def _broadcast_loop(self) -> None:
        while self._running:
            # F1: ts must refresh each iteration (payload built inside loop)
            payload = json.dumps({
                "base_id": self._base_id,
                "base_name": self._base_name,
                "port": self._server_port,
                "ts": time.time(),
            })
            try:
                assert self._send_sock is not None
                self._send_sock.sendto(payload.encode(), (BROADCAST_ADDR, self._port))
            except (OSError, AssertionError):
                pass
            await asyncio.sleep(BEACON_INTERVAL)

    # ── recv socket (C1: non-blocking + loop.sock_recvfrom) ─
    def _start_recv_socket(self) -> None:
        if self._recv_sock is not None:
            return
        self._recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._recv_sock.bind(("", self._port))
        # E2: loop.sock_recvfrom requires non-blocking socket
        self._recv_sock.setblocking(False)

    def _close_recv_socket(self) -> None:
        if self._recv_sock is not None:
            self._recv_sock.close()
            self._recv_sock = None

    async def _recv_loop(self) -> None:
        assert self._recv_sock is not None
        loop = asyncio.get_running_loop()
        while self._running:
            try:
                # C1: non-blocking via loop.sock_recvfrom (no blocking settimeout)
                data, addr = await loop.sock_recvfrom(self._recv_sock, 4096)
                msg = json.loads(data.decode())
                bid = str(msg.get("base_id", "")).strip()
                if bid and bid != self._base_id:
                    self._on_peer_discovered(msg, addr)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                pass

    # ── peer discovery with TTL ──────────────────────────────
    def _on_peer_discovered(self, msg: dict, addr: tuple) -> None:
        from services import network as net
        now = time.time()
        ttl_sec = BEACON_INTERVAL * TTL_MULTIPLIER  # 6 s
        bid = str(msg.get("base_id", "")).strip()
        if not bid or bid == self._base_id:
            return
        net.heartbeat(base_id=bid, base_name=str(msg.get("base_name", "")), ip=addr[0])
        self._discovered_peers[bid] = {
            "base_name": str(msg.get("base_name", "")),
            "ip": addr[0],
            "port": int(msg.get("port", 0)),
            "ts": float(msg.get("ts", now)),
        }
        self._prune_expired(now, ttl_sec)

    def _prune_expired(self, now: float, ttl_sec: float) -> None:
        expired = [
            bid for bid, info in self._discovered_peers.items()
            if (now - float(info["ts"])) > ttl_sec
        ]
        for bid in expired:
            del self._discovered_peers[bid]

    @property
    def discovered_peers(self) -> dict[str, dict]:
        """Live peers only (TTL-pruned)."""
        self._prune_expired(time.time(), BEACON_INTERVAL * TTL_MULTIPLIER)
        return dict(self._discovered_peers)

    @property
    def live_peer_count(self) -> int:
        return len(self.discovered_peers)


_beacon: LanBeacon | None = None


def get_beacon() -> LanBeacon | None:
    return _beacon


def start_beacon_if_enabled() -> asyncio.Task | None:
    """Called from main.py lifespan. Returns bootstrap task reference."""
    global _beacon
    from services import network as net
    cfg = net.get_config()
    _beacon = LanBeacon()
    _beacon.configure(
        enabled=bool(int(str(cfg.get("lan_beacon_enabled", "0")))),
        port=int(cfg.get("lan_beacon_port", BEACON_PORT_DEFAULT)),
        base_id=net.ensure_base_id(),
        base_name=str(cfg.get("base_name", "")),
        server_port=int(cfg.get("port", 8000)),
    )
    return asyncio.create_task(_beacon.start())


async def stop_beacon() -> None:
    global _beacon
    if _beacon:
        await _beacon.stop()


async def reconfigure_beacon(enabled: bool, port: int) -> None:
    """C7: live reconfigure on POST /api/network/config (no restart)."""
    global _beacon
    if _beacon is None:
        return
    _beacon.configure(
        enabled=enabled,
        port=port,
        base_id=_beacon._base_id,
        base_name=_beacon._base_name,
        server_port=_beacon._server_port,
    )
    if enabled:
        await _beacon.start()
    else:
        await _beacon.stop()
