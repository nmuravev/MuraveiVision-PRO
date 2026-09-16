"""In-process WebSocket hub for network chat (browser + backend peer registries)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

from services import network as net

logger = logging.getLogger("muravei.chat_ws")

_lock = asyncio.Lock()
_browsers: set[WebSocket] = set()
_peers: dict[WebSocket, dict[str, str]] = {}


def public_message(row: dict[str, Any]) -> dict[str, Any]:
    out = {
        "id": str(row.get("id") or ""),
        "created_at": float(row.get("created_at") or 0),
        "direction": str(row.get("direction") or ""),
        "sender": str(row.get("sender") or ""),
        "body": str(row.get("body") or ""),
    }
    aid = row.get("attachment_id")
    if aid:
        out["attachment_id"] = str(aid)
    return out


def envelope_message(row: dict[str, Any]) -> str:
    return json.dumps({"type": "chat.message", "message": public_message(row)})


async def register_browser(ws: WebSocket) -> None:
    async with _lock:
        _browsers.add(ws)


async def unregister_browser(ws: WebSocket) -> None:
    async with _lock:
        _browsers.discard(ws)


async def register_peer(ws: WebSocket, base_id: str, base_name: str) -> None:
    async with _lock:
        _peers[ws] = {
            "base_id": (base_id or "").strip(),
            "base_name": (base_name or "").strip(),
        }


async def unregister_peer(ws: WebSocket) -> None:
    async with _lock:
        _peers.pop(ws, None)


async def _send_many(sockets: list[WebSocket], payload: str) -> None:
    dead: list[WebSocket] = []
    for ws in sockets:
        try:
            await ws.send_text(payload)
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        await unregister_browser(ws)
        await unregister_peer(ws)


async def broadcast_browsers(payload: str) -> None:
    async with _lock:
        targets = list(_browsers)
    await _send_many(targets, payload)


async def broadcast_peers(payload: str, *, except_base_id: str | None = None) -> None:
    exc = (except_base_id or "").strip()
    async with _lock:
        targets: list[WebSocket] = []
        for ws, meta in _peers.items():
            bid = meta.get("base_id") or ""
            if exc and bid == exc:
                continue
            targets.append(ws)
    await _send_many(targets, payload)


async def emit_chat_message(row: dict[str, Any], *, relay_peers: bool = False) -> None:
    """Notify local browser WS clients; optionally relay to connected backend peers (hub)."""
    if not row.get("id"):
        return
    payload = envelope_message(row)
    await broadcast_browsers(payload)
    if relay_peers and net.get_config().get("mode") == "server":
        await broadcast_peers(payload)


def schedule_emit_chat_message(row: dict[str, Any], *, relay_peers: bool = False) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(emit_chat_message(row, relay_peers=relay_peers))


async def handle_peer_inbound(ws: WebSocket, text: str) -> None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict):
        return
    typ = str(data.get("type") or "")
    if typ == "peer.hello":
        base_id = str(data.get("base_id") or "").strip()
        base_name = str(data.get("base_name") or "").strip()
        if base_id:
            await register_peer(ws, base_id, base_name)
        return
    if typ != "chat.message":
        return
    raw = data.get("message")
    if not isinstance(raw, dict):
        return
    body = str(raw.get("body") or "").strip()
    mid = str(raw.get("id") or "").strip()
    if not mid or not body:
        return
    sender = str(raw.get("sender") or "").strip() or "База"
    created = raw.get("created_at")
    aid = str(raw.get("attachment_id") or "").strip() or None
    row = net.add_message(
        direction="out",
        sender=sender,
        body=body,
        message_id=mid,
        created_at=float(created) if created is not None else None,
        attachment_id=aid,
    )
    origin = (_peers.get(ws) or {}).get("base_id")
    payload = envelope_message(row)
    await broadcast_browsers(payload)
    await broadcast_peers(payload, except_base_id=origin)


def peer_count() -> int:
    return len(_peers)
