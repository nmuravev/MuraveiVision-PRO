"""Network bases: config, targets exchange, chat."""
from __future__ import annotations

import ipaddress
import os
import socket
import time
import uuid
from typing import Any

from services.db import _connect, init_db

TARGET_TTL_SEC = 24 * 3600


def resolve_lan_ipv4() -> str:
    """Best-effort LAN IPv4 for heartbeat advertise (no external probes).

    Order: MURAVEI_NETWORK_ADVERTISE_IP → first non-loopback RFC1918/psutil → 127.0.0.1.
    """
    env = (os.environ.get("MURAVEI_NETWORK_ADVERTISE_IP") or "").strip()
    if env:
        try:
            ipaddress.IPv4Address(env)
            return env
        except ValueError:
            pass
    candidates: list[str] = []
    try:
        import psutil

        for _name, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if getattr(a, "family", None) != socket.AF_INET:
                    continue
                ip = str(a.address or "").strip()
                if not ip or ip.startswith("127.") or ip.startswith("169.254."):
                    continue
                candidates.append(ip)
    except Exception:  # noqa: BLE001
        candidates = []
    private: list[str] = []
    other: list[str] = []
    for ip in candidates:
        try:
            addr = ipaddress.IPv4Address(ip)
        except ValueError:
            continue
        if addr.is_private:
            private.append(ip)
        elif not addr.is_loopback and not addr.is_link_local:
            other.append(ip)
    if private:
        return private[0]
    if other:
        return other[0]
    return "127.0.0.1"


def ensure_base_id() -> str:
    """Persist a UUID v4 base_id once. Empty string is invalid and is replaced."""
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT base_id FROM network_config WHERE id = 1").fetchone()
        existing = str(row["base_id"] or "").strip() if row else ""
        if existing:
            return existing
        new_id = str(uuid.uuid4())
        conn.execute(
            "UPDATE network_config SET base_id = ?, updated_at = ? WHERE id = 1",
            (new_id, time.time()),
        )
        conn.commit()
        return new_id
    finally:
        conn.close()


def get_config() -> dict[str, Any]:
    init_db()
    base_id = ensure_base_id()
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM network_config WHERE id = 1").fetchone()
        if not row:
            return {
                "mode": "off",
                "server_ip": "127.0.0.1",
                "port": 8000,
                "base_name": "База-1",
                "base_id": base_id,
            }
        keys = set(row.keys())
        return {
            "mode": str(row["mode"]),
            "server_ip": str(row["server_ip"]),
            "port": int(row["port"]),
            "base_name": str(row["base_name"]),
            "base_id": base_id,
            "updated_at": float(row["updated_at"]),
            "has_hub_pin": bool(str(row["hub_pin"] or "").strip()) if "hub_pin" in keys else False,
            "lan_beacon_enabled": bool(int(str(row["lan_beacon_enabled"] or "0"))) if "lan_beacon_enabled" in keys else False,
            "lan_beacon_port": int(row["lan_beacon_port"] or 8001) if "lan_beacon_port" in keys else 8001,
        }
    finally:
        conn.close()


def save_config(
    *,
    mode: str,
    server_ip: str,
    port: int,
    base_name: str,
    hub_pin: str | None = None,
    lan_beacon_enabled: bool = False,
    lan_beacon_port: int = 8001,
) -> dict[str, Any]:
    init_db()
    mode = mode if mode in ("off", "server", "client") else "off"
    port = max(1, min(65535, int(port)))
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO network_config (id, mode, server_ip, port, base_name, updated_at)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                mode=excluded.mode,
                server_ip=excluded.server_ip,
                port=excluded.port,
                base_name=excluded.base_name,
                updated_at=excluded.updated_at
            """,
            (mode, server_ip.strip() or "127.0.0.1", port, base_name.strip() or "База-1", time.time()),
        )
        # C7: persist beacon fields
        conn.execute(
            "UPDATE network_config SET lan_beacon_enabled = ?, lan_beacon_port = ? WHERE id = 1",
            ("1" if lan_beacon_enabled else "0", lan_beacon_port),
        )
        pin = (hub_pin or "").strip()
        if pin:
            conn.execute(
                "UPDATE network_config SET hub_pin = ? WHERE id = 1",
                (pin,),
            )
        conn.commit()
    finally:
        conn.close()
    return get_config()


def get_hub_pin() -> str:
    """Return stored hub PIN. Never expose via GET /config."""
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT hub_pin FROM network_config WHERE id = 1").fetchone()
        return str(row["hub_pin"] or "").strip() if row else ""
    finally:
        conn.close()


def heartbeat(base_id: str, base_name: str, ip: str) -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO network_bases (id, base_name, ip, last_seen, status)
            VALUES (?, ?, ?, ?, 'online')
            ON CONFLICT(id) DO UPDATE SET
                base_name=excluded.base_name,
                ip=excluded.ip,
                last_seen=excluded.last_seen,
                status='online'
            """,
            (base_id, base_name, ip, time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def list_bases() -> list[dict[str, Any]]:
    init_db()
    purge_stale()
    conn = _connect()
    try:
        now = time.time()
        rows = conn.execute(
            "SELECT * FROM network_bases ORDER BY last_seen DESC LIMIT 50"
        ).fetchall()
        out = []
        for r in rows:
            age = now - float(r["last_seen"])
            status = "online" if age < 120 else "offline"
            out.append(
                {
                    "id": r["id"],
                    "base_name": r["base_name"],
                    "ip": r["ip"],
                    "last_seen": r["last_seen"],
                    "status": status,
                }
            )
        return out
    finally:
        conn.close()


def purge_stale() -> None:
    init_db()
    cutoff = time.time() - TARGET_TTL_SEC
    conn = _connect()
    try:
        conn.execute("DELETE FROM network_targets WHERE expires_at IS NOT NULL AND expires_at < ?", (cutoff,))
        conn.execute("DELETE FROM network_targets WHERE created_at < ?", (cutoff,))
        conn.execute("DELETE FROM network_messages WHERE expires_at IS NOT NULL AND expires_at < ?", (cutoff,))
        conn.execute("DELETE FROM network_messages WHERE created_at < ?", (cutoff,))
        conn.execute("DELETE FROM network_bases WHERE last_seen < ?", (time.time() - 7 * 86400,))
        conn.commit()
    finally:
        conn.close()


def add_target(
    *,
    direction: str,
    class_name: str,
    confidence: float = 0.0,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    crop_path: str | None = None,
    source_base: str | None = None,
    source_video: str | None = None,
    notes: str | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    init_db()
    tid = (target_id or "").strip() or str(uuid.uuid4())
    now = time.time()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO network_targets (
                id, created_at, direction, class_name, confidence,
                gps_lat, gps_lon, crop_path, source_base, source_video, notes, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tid,
                now,
                direction,
                class_name,
                float(confidence),
                gps_lat,
                gps_lon,
                crop_path,
                source_base,
                source_video,
                notes,
                now + TARGET_TTL_SEC,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_target(tid) or {"id": tid}


def get_target(tid: str) -> dict[str, Any] | None:
    init_db()
    conn = _connect()
    try:
        r = conn.execute("SELECT * FROM network_targets WHERE id = ?", (tid,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def upsert_target(
    *,
    class_name: str,
    confidence: float = 0.0,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    crop_path: str | None = None,
    source_base: str | None = None,
    source_video: str | None = None,
    notes: str | None = None,
    target_id: str | None = None,
    created_at: float | None = None,
    expires_at: float | None = None,
) -> dict[str, Any]:
    """Insert incoming replica, or update if incoming created_at is strictly newer."""
    init_db()
    tid = (target_id or "").strip() or str(uuid.uuid4())
    ts = float(created_at) if created_at is not None else time.time()
    exp = float(expires_at) if expires_at is not None else ts + TARGET_TTL_SEC
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO network_targets (
                id, created_at, direction, class_name, confidence,
                gps_lat, gps_lon, crop_path, source_base, source_video,
                notes, expires_at, synced_at
            ) VALUES (?, ?, 'in', ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(id) DO UPDATE SET
                created_at = excluded.created_at,
                direction = excluded.direction,
                class_name = excluded.class_name,
                confidence = excluded.confidence,
                gps_lat = excluded.gps_lat,
                gps_lon = excluded.gps_lon,
                crop_path = excluded.crop_path,
                source_base = excluded.source_base,
                source_video = excluded.source_video,
                notes = excluded.notes,
                expires_at = excluded.expires_at
            WHERE excluded.created_at > network_targets.created_at
            """,
            (
                tid,
                ts,
                class_name,
                float(confidence),
                gps_lat,
                gps_lon,
                crop_path,
                source_base,
                source_video,
                notes,
                exp,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return get_target(tid) or {"id": tid}


def list_targets(limit: int = 100, since: float | None = None) -> list[dict[str, Any]]:
    init_db()
    purge_stale()
    conn = _connect()
    try:
        limit_n = max(1, min(limit, 500))
        if since is not None:
            rows = conn.execute(
                """
                SELECT * FROM network_targets
                WHERE created_at > ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (float(since), limit_n),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM network_targets ORDER BY created_at DESC LIMIT ?",
                (limit_n,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_unsynced_out_targets(limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM network_targets
            WHERE direction = 'out' AND synced_at IS NULL
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (max(1, min(limit, 200)),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_target_synced(tid: str, ts: float | None = None) -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute(
            "UPDATE network_targets SET synced_at = ? WHERE id = ?",
            (float(ts if ts is not None else time.time()), tid),
        )
        conn.commit()
    finally:
        conn.close()


def list_recent_incoming_targets(since: float, limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM network_targets
            WHERE direction = 'in' AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (float(since), max(1, min(int(limit), 500))),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_message(
    *,
    direction: str,
    sender: str,
    body: str,
    message_id: str | None = None,
    created_at: float | None = None,
    attachment_id: str | None = None,
) -> dict[str, Any]:
    """Insert outgoing (or hub-received) message. Duplicate id is idempotent (no overwrite)."""
    init_db()
    mid = (message_id or "").strip() or str(uuid.uuid4())
    now = float(created_at) if created_at is not None else time.time()
    aid = (attachment_id or "").strip() or None
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO network_messages (
                id, created_at, direction, sender, body, expires_at, synced_at, attachment_id
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (mid, now, direction, sender, body.strip(), now + TARGET_TTL_SEC, aid),
        )
        conn.commit()
    finally:
        conn.close()
    return get_message(mid) or {
        "id": mid,
        "created_at": now,
        "direction": direction,
        "sender": sender,
        "body": body.strip(),
        "expires_at": now + TARGET_TTL_SEC,
        "synced_at": None,
        "attachment_id": aid,
    }


def get_message(mid: str) -> dict[str, Any] | None:
    init_db()
    conn = _connect()
    try:
        r = conn.execute("SELECT * FROM network_messages WHERE id = ?", (mid,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def upsert_message(
    *,
    sender: str,
    body: str,
    message_id: str | None = None,
    created_at: float | None = None,
    expires_at: float | None = None,
    attachment_id: str | None = None,
) -> dict[str, Any]:
    """Insert incoming replica as direction=in, or update if incoming created_at is newer."""
    init_db()
    mid = (message_id or "").strip() or str(uuid.uuid4())
    ts = float(created_at) if created_at is not None else time.time()
    exp = float(expires_at) if expires_at is not None else ts + TARGET_TTL_SEC
    aid = (attachment_id or "").strip() or None
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO network_messages (
                id, created_at, direction, sender, body, expires_at, synced_at, attachment_id
            ) VALUES (?, ?, 'in', ?, ?, ?, NULL, ?)
            ON CONFLICT(id) DO UPDATE SET
                created_at = excluded.created_at,
                direction = excluded.direction,
                sender = excluded.sender,
                body = excluded.body,
                expires_at = excluded.expires_at,
                attachment_id = COALESCE(excluded.attachment_id, network_messages.attachment_id)
            WHERE excluded.created_at > network_messages.created_at
            """,
            (mid, ts, sender, body.strip(), exp, aid),
        )
        conn.commit()
    finally:
        conn.close()
    return get_message(mid) or {"id": mid}


def list_messages(limit: int = 100, since: float | None = None) -> list[dict[str, Any]]:
    init_db()
    purge_stale()
    conn = _connect()
    try:
        limit_n = max(1, min(limit, 500))
        if since is not None:
            rows = conn.execute(
                """
                SELECT * FROM network_messages
                WHERE created_at > ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (float(since), limit_n),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM network_messages ORDER BY created_at DESC LIMIT ?",
                (limit_n,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_unsynced_out_messages(limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM network_messages
            WHERE direction = 'out' AND synced_at IS NULL
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (max(1, min(limit, 200)),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_message_synced(mid: str, ts: float | None = None) -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute(
            "UPDATE network_messages SET synced_at = ? WHERE id = ?",
            (float(ts if ts is not None else time.time()), mid),
        )
        conn.commit()
    finally:
        conn.close()


def count_incoming_messages_since(since: float) -> int:
    """Unread helper: count direction=in with created_at > since."""
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS n FROM network_messages
            WHERE direction = 'in' AND created_at > ?
            """,
            (float(since),),
        ).fetchone()
        return int(row["n"] if row else 0)
    finally:
        conn.close()
