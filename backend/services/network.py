"""Network bases: config, targets exchange, chat (Variant A — same API host)."""
from __future__ import annotations

import time
import uuid
from typing import Any

from services.db import _connect, init_db

TARGET_TTL_SEC = 24 * 3600


def get_config() -> dict[str, Any]:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM network_config WHERE id = 1").fetchone()
        if not row:
            return {
                "mode": "off",
                "server_ip": "127.0.0.1",
                "port": 8000,
                "base_name": "База-1",
            }
        return {
            "mode": str(row["mode"]),
            "server_ip": str(row["server_ip"]),
            "port": int(row["port"]),
            "base_name": str(row["base_name"]),
            "updated_at": float(row["updated_at"]),
        }
    finally:
        conn.close()


def save_config(
    *,
    mode: str,
    server_ip: str,
    port: int,
    base_name: str,
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
        conn.commit()
    finally:
        conn.close()
    return get_config()


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
) -> dict[str, Any]:
    init_db()
    tid = str(uuid.uuid4())
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


def list_targets(limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    purge_stale()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM network_targets ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_message(*, direction: str, sender: str, body: str) -> dict[str, Any]:
    init_db()
    mid = str(uuid.uuid4())
    now = time.time()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO network_messages (id, created_at, direction, sender, body)
            VALUES (?, ?, ?, ?, ?)
            """,
            (mid, now, direction, sender, body.strip()),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "id": mid,
        "created_at": now,
        "direction": direction,
        "sender": sender,
        "body": body.strip(),
    }


def list_messages(limit: int = 100) -> list[dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM network_messages ORDER BY created_at DESC LIMIT ?",
            (max(1, min(limit, 500)),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
