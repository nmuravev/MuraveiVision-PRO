"""SQLite: pins, settings, lockouts, and operator detections."""
from __future__ import annotations

import logging
import base64
import hashlib
import io
import json
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Project root (MuraveiVision-PRO/) — backend/services/<file>.py → parents[2]
BASE_DIR = Path(__file__).resolve().parents[2]

DB_PATH: Path = BASE_DIR / "muravei.db"
CROPS_DIR: Path = BASE_DIR / "archive" / "crops"

DEFAULT_PINS: dict[str, str] = {
    "operator": "1234567",
    "engineer": "0000000",
    "master": "0987907",
}

_lock = threading.Lock()
_initialized = False
_jwt_secret_cache: str | None = None

# P1-2: Lock for write operations (INSERT/UPDATE/DELETE)
# READ operations (SELECT) can run concurrently in WAL mode
_write_lock = threading.Lock()


def normalize_media_path(path: str) -> str:
    """Canonical source_video key: forward slashes, relative to archive/ (no prefix)."""
    if not path:
        return ""
    p = str(path).replace("\\", "/").strip()
    while "//" in p:
        p = p.replace("//", "/")
    lower = p.lower()
    marker = "/archive/"
    idx = lower.find(marker)
    if idx >= 0:
        p = p[idx + len(marker) :]
    elif lower.startswith("archive/"):
        p = p[len("archive/") :]
    return p.lstrip("/")


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def pin_b64(pin: str) -> str:
    return base64.b64encode(pin.encode("utf-8")).decode("ascii")


def pin_from_b64(encoded: str) -> str:
    return base64.b64decode(encoded.encode("ascii")).decode("utf-8")


# P1-11: WAL checkpoint counter
_wal_checkpoint_counter = 0
_wal_checkpoint_lock = threading.Lock()
_WAL_CHECKPOINT_INTERVAL = 1000  # checkpoint every N writes


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # P1-11: Enable auto-checkpoint at 1000 pages (~8MB)
    conn.execute("PRAGMA wal_autocheckpoint=1000")
    return conn


def checkpoint_wal(conn: sqlite3.Connection) -> None:
    """Perform explicit WAL checkpoint to prevent WAL file growth.

    P1-11: Called periodically to truncate WAL and SHM files.
    Uses PASSIVE mode — waits for readers to finish.
    """
    global _wal_checkpoint_counter
    with _wal_checkpoint_lock:
        _wal_checkpoint_counter += 1
        if _wal_checkpoint_counter >= _WAL_CHECKPOINT_INTERVAL:
            _wal_checkpoint_counter = 0
            try:
                conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except Exception:
                pass


def init_db() -> None:
    """Create schema and seed factory PIN/JWT defaults once per process."""
    global _initialized
    with _lock:
        if _initialized:
            return
        CROPS_DIR.mkdir(parents=True, exist_ok=True)
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS pins (
                    role TEXT PRIMARY KEY,
                    pin_sha256 TEXT NOT NULL,
                    pin_b64 TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS lockouts (
                    client_key TEXT PRIMARY KEY,
                    fail_count INTEGER NOT NULL DEFAULT 0,
                    locked_until REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS detections (
                    id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    source_video TEXT NOT NULL,
                    time_sec REAL NOT NULL,
                    frame_idx INTEGER NOT NULL DEFAULT 0,
                    class_id INTEGER NOT NULL DEFAULT 0,
                    class_name TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    bbox_x REAL NOT NULL,
                    bbox_y REAL NOT NULL,
                    bbox_w REAL NOT NULL,
                    bbox_h REAL NOT NULL,
                    crop_path TEXT,
                    is_edited INTEGER NOT NULL DEFAULT 0,
                    edited_by TEXT,
                    edited_at REAL,
                    user_notes TEXT,
                    is_deleted INTEGER NOT NULL DEFAULT 0,
                    origin TEXT NOT NULL DEFAULT 'auto',
                    ai_class_name TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_det_source_time
                    ON detections(source_video, time_sec);
                CREATE INDEX IF NOT EXISTS idx_det_class ON detections(class_name);
                CREATE INDEX IF NOT EXISTS idx_det_notes ON detections(user_notes);
                CREATE INDEX IF NOT EXISTS idx_det_created ON detections(created_at DESC);
                CREATE TABLE IF NOT EXISTS network_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    mode TEXT NOT NULL DEFAULT 'off',
                    server_ip TEXT NOT NULL DEFAULT '127.0.0.1',
                    port INTEGER NOT NULL DEFAULT 8000,
                    base_name TEXT NOT NULL DEFAULT 'База-1',
                    updated_at REAL NOT NULL,
                    hub_pin TEXT,
                    base_id TEXT
                );
                CREATE TABLE IF NOT EXISTS network_bases (
                    id TEXT PRIMARY KEY,
                    base_name TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    last_seen REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'online'
                );
                CREATE TABLE IF NOT EXISTS network_targets (
                    id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    direction TEXT NOT NULL,
                    class_name TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0,
                    gps_lat REAL,
                    gps_lon REAL,
                    crop_path TEXT,
                    source_base TEXT,
                    source_video TEXT,
                    notes TEXT,
                    expires_at REAL,
                    synced_at REAL
                );
                CREATE TABLE IF NOT EXISTS network_messages (
                    id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    direction TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    body TEXT NOT NULL,
                    expires_at REAL,
                    synced_at REAL,
                    attachment_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_net_targets_created
                    ON network_targets(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_net_messages_created
                    ON network_messages(created_at DESC);
                CREATE TABLE IF NOT EXISTS class_overrides (
                    class_id INTEGER PRIMARY KEY,
                    name_ru TEXT NOT NULL DEFAULT '',
                    aliases TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    in_prompt INTEGER NOT NULL DEFAULT 0,
                    confidence_threshold REAL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS excluded_classes (
                    class_name TEXT PRIMARY KEY,
                    added_at REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS flight_tracks (
                    id TEXT PRIMARY KEY,
                    video_path TEXT NOT NULL UNIQUE,
                    track_data TEXT NOT NULL DEFAULT '[]',
                    source_file TEXT,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_flight_tracks_video
                    ON flight_tracks(video_path);
                CREATE TABLE IF NOT EXISTS active_learning_samples (
                    id TEXT PRIMARY KEY,
                    detection_id TEXT NOT NULL,
                    source_video TEXT NOT NULL,
                    time_sec REAL NOT NULL,
                    feedback_type TEXT NOT NULL,
                    proposed_class TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(detection_id, feedback_type)
                );
                CREATE INDEX IF NOT EXISTS idx_active_learning_status
                    ON active_learning_samples(status, created_at DESC);
                CREATE TABLE IF NOT EXISTS detection_embeddings (
                    detection_id TEXT PRIMARY KEY,
                    method TEXT NOT NULL,
                    crop_mtime REAL NOT NULL,
                    dim INTEGER NOT NULL,
                    embedding BLOB NOT NULL,
                    computed_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS seg_masks (
                    id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    source_video TEXT NOT NULL,
                    time_sec REAL NOT NULL,
                    frame_idx INTEGER NOT NULL DEFAULT 0,
                    class_name TEXT NOT NULL DEFAULT 'object',
                    confidence REAL NOT NULL DEFAULT 1.0,
                    polygon_json TEXT NOT NULL,
                    origin TEXT NOT NULL DEFAULT 'sam3',
                    track_id TEXT,
                    is_deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_seg_masks_source_time
                    ON seg_masks(source_video, time_sec);
                CREATE INDEX IF NOT EXISTS idx_seg_masks_track
                    ON seg_masks(track_id);
                """
            )
            cols = {r[1] for r in conn.execute("PRAGMA table_info(detections)").fetchall()}
            if "ai_class_name" not in cols:
                conn.execute("ALTER TABLE detections ADD COLUMN ai_class_name TEXT")
            for gps_col in ("gps_lat", "gps_lon", "gps_alt"):
                if gps_col not in cols:
                    conn.execute(f"ALTER TABLE detections ADD COLUMN {gps_col} REAL")
            network_target_cols = {
                r[1] for r in conn.execute("PRAGMA table_info(network_targets)").fetchall()
            }
            if "source_video" not in network_target_cols:
                conn.execute("ALTER TABLE network_targets ADD COLUMN source_video TEXT")
            if "synced_at" not in network_target_cols:
                conn.execute("ALTER TABLE network_targets ADD COLUMN synced_at REAL")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_net_targets_synced ON network_targets(synced_at)"
            )
            network_message_cols = {
                r[1] for r in conn.execute("PRAGMA table_info(network_messages)").fetchall()
            }
            if "synced_at" not in network_message_cols:
                conn.execute("ALTER TABLE network_messages ADD COLUMN synced_at REAL")
            if "expires_at" not in network_message_cols:
                conn.execute("ALTER TABLE network_messages ADD COLUMN expires_at REAL")
            if "attachment_id" not in network_message_cols:
                conn.execute("ALTER TABLE network_messages ADD COLUMN attachment_id TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_net_messages_synced ON network_messages(synced_at)"
            )
            network_config_cols = {
                r[1] for r in conn.execute("PRAGMA table_info(network_config)").fetchall()
            }
            if "hub_pin" not in network_config_cols:
                conn.execute("ALTER TABLE network_config ADD COLUMN hub_pin TEXT")
            if "base_id" not in network_config_cols:
                conn.execute("ALTER TABLE network_config ADD COLUMN base_id TEXT")
            if "lan_beacon_enabled" not in network_config_cols:
                conn.execute("ALTER TABLE network_config ADD COLUMN lan_beacon_enabled TEXT DEFAULT '0'")
            if "lan_beacon_port" not in network_config_cols:
                conn.execute("ALTER TABLE network_config ADD COLUMN lan_beacon_port INTEGER DEFAULT 8001")
            override_cols = {
                r[1] for r in conn.execute("PRAGMA table_info(class_overrides)").fetchall()
            }
            if "confidence_threshold" not in override_cols:
                conn.execute(
                    "ALTER TABLE class_overrides ADD COLUMN confidence_threshold REAL"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_det_created ON detections(created_at DESC)"
            )
            conn.execute(
                """
                UPDATE detections
                SET ai_class_name = class_name
                WHERE ai_class_name IS NULL OR ai_class_name = ''
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO network_config (id, mode, server_ip, port, base_name, updated_at)
                VALUES (1, 'off', '127.0.0.1', 8000, 'База-1', ?)
                """,
                (time.time(),),
            )
            now = time.time()
            for role, pin in DEFAULT_PINS.items():
                conn.execute(
                    """
                    INSERT OR IGNORE INTO pins (role, pin_sha256, pin_b64, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (role, sha256_hex(pin), pin_b64(pin), now),
                )
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES ('jwt_secret', ?)",
                (secrets.token_hex(32),),
            )
            conn.commit()
        finally:
            conn.close()
        _initialized = True
        print(f"[DB] Ready at {DB_PATH}")


def get_setting(key: str, default: str | None = None) -> str | None:
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return default
        return str(row["value"])
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    init_db()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def get_jwt_secret() -> str:
    """Read the secret created once in init_db(). Never rotate on later boots."""
    global _jwt_secret_cache
    if _jwt_secret_cache:
        return _jwt_secret_cache
    secret = get_setting("jwt_secret")
    if not secret:
        raise RuntimeError("jwt_secret missing from settings after init_db()")
    _jwt_secret_cache = secret
    return secret


def get_pin_row(role: str) -> dict[str, Any] | None:
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT role, pin_sha256, pin_b64, updated_at FROM pins WHERE role = ?",
            (role,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_pin_roles() -> list[str]:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute("SELECT role FROM pins ORDER BY role").fetchall()
        return [str(r["role"]) for r in rows]
    finally:
        conn.close()


def find_role_by_pin(pin: str) -> str | None:
    digest = sha256_hex(pin)
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT role FROM pins WHERE pin_sha256 = ?", (digest,)
        ).fetchone()
        return str(row["role"]) if row else None
    finally:
        conn.close()


def update_pin(role: str, pin: str) -> None:
    init_db()
    # P1-2: Lock for write operation
    with _write_lock:
        conn = _connect()
        try:
            conn.execute(
                """
                UPDATE pins
                SET pin_sha256 = ?, pin_b64 = ?, updated_at = ?
                WHERE role = ?
                """,
                (sha256_hex(pin), pin_b64(pin), time.time(), role),
            )
            conn.commit()
        finally:
            conn.close()


def get_lockout(client_key: str) -> dict[str, Any]:
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT fail_count, locked_until FROM lockouts WHERE client_key = ?",
            (client_key,),
        ).fetchone()
        if row is None:
            return {"fail_count": 0, "locked_until": 0.0}
        return {
            "fail_count": int(row["fail_count"]),
            "locked_until": float(row["locked_until"]),
        }
    finally:
        conn.close()


MAX_LOCKOUT_RETRIES = 3
LOCKOUT_RETRY_BACKOFF = 0.05  # 50ms


def record_failed_login(client_key: str, max_fails: int = 5, lock_sec: int = 120) -> dict[str, Any]:
    """Atomically increment fail_count and lock if threshold reached.

    Uses atomic SQL UPDATE (fail_count = fail_count + 1) to prevent
    race conditions under concurrent brute-force attacks.

    Includes retry logic for sqlite3.OperationalError: database is locked.

    Args:
        client_key: Client identifier (IP or key)
        max_fails: Number of failures before lockout
        lock_sec: Lockout duration in seconds

    Returns:
        Dict with fail_count and locked_until timestamp
    """
    init_db()
    now = time.time()

    # P1-2: Lock for write operation
    with _write_lock:
        for attempt in range(MAX_LOCKOUT_RETRIES):
            conn = _connect()
            try:
                # Atomic SQL: increment fail_count directly in DB
                # No read-modify-write race condition
                conn.execute(
                    """
                    INSERT INTO lockouts (client_key, fail_count, locked_until)
                    VALUES (?, 1, 0)
                    ON CONFLICT(client_key) DO UPDATE SET
                        fail_count = fail_count + 1,
                        locked_until = CASE
                            WHEN fail_count + 1 >= ? THEN ?
                            ELSE locked_until
                        END
                    """,
                    (client_key, max_fails, now + lock_sec),
                )
                conn.commit()

                # Read updated fail_count
                row = conn.execute(
                    "SELECT fail_count, locked_until FROM lockouts WHERE client_key = ?",
                    (client_key,),
                ).fetchone()

                fail_count = int(row["fail_count"]) if row else 1
                locked_until = float(row["locked_until"]) if row else 0.0

                return {"fail_count": fail_count, "locked_until": locked_until}

            except sqlite3.OperationalError as exc:
                if "database is locked" in str(exc) and attempt < MAX_LOCKOUT_RETRIES - 1:
                    conn.close()
                    time.sleep(LOCKOUT_RETRY_BACKOFF * (2 ** attempt))
                    logger.warning(
                        f"[LOCKOUT] Database locked (attempt {attempt + 1}/{MAX_LOCKOUT_RETRIES}), "
                        f"retrying for client {client_key}"
                    )
                    continue
                raise
            finally:
                conn.close()


def clear_lockout(client_key: str) -> None:
    init_db()
    # P1-2: Lock for write operation
    with _write_lock:
        conn = _connect()
        try:
            conn.execute("DELETE FROM lockouts WHERE client_key = ?", (client_key,))
            conn.commit()
        finally:
            conn.close()


def _row_keys(row: sqlite3.Row) -> set[str]:
    return set(row.keys())


def _row_gps(row: sqlite3.Row, key: str) -> float | None:
    if key not in _row_keys(row):
        return None
    val = row[key]
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _row_to_detection(row: sqlite3.Row) -> dict[str, Any]:
    keys = _row_keys(row)
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "source_video": row["source_video"],
        "time_sec": row["time_sec"],
        "frame_idx": row["frame_idx"],
        "class_id": row["class_id"],
        "class_name": row["class_name"],
        "confidence": row["confidence"],
        "bbox_x": row["bbox_x"],
        "bbox_y": row["bbox_y"],
        "bbox_w": row["bbox_w"],
        "bbox_h": row["bbox_h"],
        "crop_path": row["crop_path"],
        "is_edited": bool(row["is_edited"]),
        "edited_by": row["edited_by"],
        "edited_at": row["edited_at"],
        "user_notes": row["user_notes"] or "",
        "is_deleted": bool(row["is_deleted"]),
        "origin": row["origin"],
        "ai_class_name": row["ai_class_name"] if "ai_class_name" in keys else row["class_name"],
        "gps_lat": _row_gps(row, "gps_lat"),
        "gps_lon": _row_gps(row, "gps_lon"),
        "gps_alt": _row_gps(row, "gps_alt"),
    }


def save_crop_jpeg(detection_id: str, jpeg_bytes: bytes, bbox: dict[str, float]) -> str | None:
    """Crop bbox (normalized x,y,w,h) from a JPEG frame into archive/crops/{id}.jpg."""
    if not jpeg_bytes:
        return None
    try:
        from PIL import Image
    except ImportError:
        print("[DB] Pillow missing — crop not saved")
        return None
    CROPS_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
    w, h = img.size
    if w <= 0 or h <= 0:
        print(f"[DB] crop rejected: empty image for {detection_id}")
        return None
    try:
        bx = float(bbox["x"])
        by = float(bbox["y"])
        bw = float(bbox["w"])
        bh = float(bbox["h"])
    except (KeyError, TypeError, ValueError) as exc:
        print(f"[DB] crop rejected: bad bbox for {detection_id}: {exc}")
        return None
    if bw <= 0 or bh <= 0:
        print(f"[DB] crop rejected: non-positive bbox size id={detection_id} w={bw} h={bh}")
        return None
    x1 = int(bx * w)
    y1 = int(by * h)
    x2 = int((bx + bw) * w)
    y2 = int((by + bh) * h)
    # Hard clamp to [0, W] / [0, H] (PIL crop end exclusive at W/H).
    x1 = max(0, min(w, x1))
    y1 = max(0, min(h, y1))
    x2 = max(0, min(w, x2))
    y2 = max(0, min(h, y2))
    cw = x2 - x1
    ch = y2 - y1
    if cw <= 0 or ch <= 0:
        print(
            f"[DB] crop rejected: non-positive size after clamp "
            f"id={detection_id} box=({x1},{y1},{x2},{y2}) frame={w}x{h}"
        )
        return None
    crop = img.crop((x1, y1, x2, y2))
    dest = CROPS_DIR / f"{detection_id}.jpg"
    crop.save(dest, format="JPEG", quality=85)
    # Store archive-relative key (not absolute) so media resolve is CWD-safe
    return f"crops/{detection_id}.jpg"


def insert_detection(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    det_id = str(payload.get("id") or uuid.uuid4())
    now = time.time()
    gps_lat = payload.get("gps_lat")
    gps_lon = payload.get("gps_lon")
    gps_alt = payload.get("gps_alt")
    source_video = normalize_media_path(str(payload.get("source_video") or ""))
    # P1-2: Lock for write operation
    with _write_lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO detections (
                    id, created_at, source_video, time_sec, frame_idx,
                    class_id, class_name, confidence,
                    bbox_x, bbox_y, bbox_w, bbox_h, crop_path,
                    is_edited, edited_by, edited_at, user_notes, is_deleted, origin,
                    ai_class_name, gps_lat, gps_lon, gps_alt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    det_id,
                    now,
                    source_video,
                    float(payload["time_sec"]),
                    int(payload.get("frame_idx") or 0),
                    int(payload.get("class_id") or 0),
                    str(payload["class_name"]),
                    float(payload.get("confidence") if payload.get("confidence") is not None else 1.0),
                    float(payload["bbox_x"]),
                    float(payload["bbox_y"]),
                    float(payload["bbox_w"]),
                    float(payload["bbox_h"]),
                    payload.get("crop_path"),
                    1 if payload.get("is_edited") else 0,
                    payload.get("edited_by"),
                    payload.get("edited_at"),
                    payload.get("user_notes") or "",
                    1 if payload.get("is_deleted") else 0,
                    payload.get("origin") or "auto",
                    str(payload.get("ai_class_name") or payload["class_name"]),
                    float(gps_lat) if gps_lat is not None else None,
                    float(gps_lon) if gps_lon is not None else None,
                    float(gps_alt) if gps_alt is not None else None,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM detections WHERE id = ?", (det_id,)).fetchone()
            return _row_to_detection(row)
        finally:
            conn.close()


def get_detection(det_id: str) -> dict[str, Any] | None:
    init_db()
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM detections WHERE id = ?", (det_id,)).fetchone()
        return _row_to_detection(row) if row else None
    finally:
        conn.close()


def list_detections(
    source_video: str | None = None,
    class_name: str | None = None,
    q: str | None = None,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    init_db()
    clauses: list[str] = []
    args: list[Any] = []
    if not include_deleted:
        clauses.append("is_deleted = 0")
    source_key = normalize_media_path(source_video) if source_video else None
    if source_key:
        # Match normalized key and legacy slash / archive-prefix variants.
        clauses.append(
            """(
                REPLACE(source_video, '\\', '/') = ?
                OR REPLACE(source_video, '\\', '/') = ?
                OR REPLACE(REPLACE(source_video, '\\', '/'), 'archive/', '') = ?
            )"""
        )
        args.extend([source_key, f"archive/{source_key}", source_key])
    if class_name:
        clauses.append("class_name = ?")
        args.append(class_name)
    if q:
        clauses.append("(user_notes LIKE ? OR class_name LIKE ?)")
        like = f"%{q}%"
        args.extend([like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = _connect()
    try:
        rows = conn.execute(
            f"SELECT * FROM detections {where} ORDER BY time_sec ASC, created_at ASC",
            args,
        ).fetchall()
        out = [_row_to_detection(r) for r in rows]
        if source_key:
            out = [r for r in out if normalize_media_path(str(r.get("source_video") or "")) == source_key]
        return out
    finally:
        conn.close()


def list_recent_detections(since: float, limit: int = 100) -> list[dict[str, Any]]:
    """Non-deleted detections with created_at >= since, newest first."""
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM detections
            WHERE is_deleted = 0 AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (float(since), max(1, min(int(limit), 500))),
        ).fetchall()
        return [_row_to_detection(r) for r in rows]
    finally:
        conn.close()


def update_detection(det_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    init_db()
    allowed = {
        "class_id",
        "class_name",
        "confidence",
        "bbox_x",
        "bbox_y",
        "bbox_w",
        "bbox_h",
        "crop_path",
        "is_edited",
        "edited_by",
        "edited_at",
        "user_notes",
        "is_deleted",
        "origin",
        "gps_lat",
        "gps_lon",
        "gps_alt",
        "ai_class_name",
    }
    sets: list[str] = []
    args: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key in {"is_edited", "is_deleted"}:
            value = 1 if value else 0
        sets.append(f"{key} = ?")
        args.append(value)
    if not sets:
        return get_detection(det_id)
    args.append(det_id)
    conn = _connect()
    try:
        conn.execute(f"UPDATE detections SET {', '.join(sets)} WHERE id = ?", args)
        conn.commit()
        row = conn.execute("SELECT * FROM detections WHERE id = ?", (det_id,)).fetchone()
        return _row_to_detection(row) if row else None
    finally:
        conn.close()


def soft_delete_detection(det_id: str, edited_by: str | None) -> dict[str, Any] | None:
    return update_detection(
        det_id,
        {
            "is_deleted": 1,
            "is_edited": 1,
            "edited_by": edited_by,
            "edited_at": time.time(),
        },
    )


def insert_seg_masks_batch(rows: list[dict[str, Any]]) -> int:
    """Insert SAM/seg polygons. Never touches detections/train."""
    if not rows:
        return 0
    init_db()
    now = time.time()
    conn = _connect()
    n = 0
    try:
        for row in rows:
            poly = row.get("polygon_norm") or []
            if not isinstance(poly, list) or len(poly) < 3:
                continue
            mid = str(row.get("id") or uuid.uuid4())
            source = normalize_media_path(str(row.get("source_video") or ""))
            conn.execute(
                """
                INSERT INTO seg_masks (
                    id, created_at, source_video, time_sec, frame_idx,
                    class_name, confidence, polygon_json, origin, track_id, is_deleted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    mid,
                    now,
                    source,
                    float(row.get("time_sec") or 0.0),
                    int(row.get("frame_idx") or 0),
                    str(row.get("class_name") or "object"),
                    float(
                        row.get("confidence")
                        if row.get("confidence") is not None
                        else 1.0
                    ),
                    json.dumps(poly, ensure_ascii=False),
                    str(row.get("origin") or "sam3"),
                    row.get("track_id"),
                ),
            )
            n += 1
        conn.commit()
        return n
    finally:
        conn.close()


def list_seg_masks(
    source_video: str,
    *,
    time_from: float | None = None,
    time_to: float | None = None,
    track_id: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    init_db()
    key = normalize_media_path(source_video)
    clauses = ["source_video = ?", "is_deleted = 0"]
    args: list[Any] = [key]
    if time_from is not None:
        clauses.append("time_sec >= ?")
        args.append(float(time_from))
    if time_to is not None:
        clauses.append("time_sec <= ?")
        args.append(float(time_to))
    if track_id:
        clauses.append("track_id = ?")
        args.append(str(track_id))
    args.append(max(1, min(5000, int(limit))))
    where = " AND ".join(clauses)
    conn = _connect()
    try:
        cur = conn.execute(
            f"""
            SELECT * FROM seg_masks
            WHERE {where}
            ORDER BY time_sec ASC, created_at ASC
            LIMIT ?
            """,
            args,
        )
        out: list[dict[str, Any]] = []
        for row in cur.fetchall():
            try:
                poly = json.loads(row["polygon_json"] or "[]")
            except json.JSONDecodeError:
                poly = []
            out.append(
                {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "source_video": row["source_video"],
                    "time_sec": row["time_sec"],
                    "frame_idx": row["frame_idx"],
                    "class_name": row["class_name"],
                    "confidence": row["confidence"],
                    "polygon_norm": poly,
                    "origin": row["origin"],
                    "track_id": row["track_id"],
                }
            )
        return out
    finally:
        conn.close()


def soft_delete_seg_masks_by_track(track_id: str) -> int:
    init_db()
    tid = (track_id or "").strip()
    if not tid:
        return 0
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE seg_masks SET is_deleted = 1 WHERE track_id = ? AND is_deleted = 0",
            (tid,),
        )
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def archive_media_exists(source_video: str) -> bool:
    """True if normalized source_video resolves to an existing file under archive/."""
    key = normalize_media_path(source_video)
    if not key:
        return False
    root = (BASE_DIR / "archive").resolve()
    try:
        target = (root / key).resolve()
        target.relative_to(root)
    except (ValueError, OSError):
        return False
    return target.is_file()


def soft_delete_detections_for_source(source_video: str, edited_by: str | None) -> int:
    """Soft-delete all non-deleted detections for a normalized source_video key."""
    key = normalize_media_path(source_video)
    if not key:
        return 0
    init_db()
    now = time.time()
    conn = _connect()
    try:
        # Match normalized + legacy archive/ and slash variants
        cur = conn.execute(
            """
            UPDATE detections
            SET is_deleted = 1, is_edited = 1, edited_by = ?, edited_at = ?
            WHERE is_deleted = 0
              AND (
                REPLACE(source_video, '\\', '/') = ?
                OR REPLACE(source_video, '\\', '/') = ?
                OR REPLACE(REPLACE(source_video, '\\', '/'), 'archive/', '') = ?
              )
            """,
            (edited_by, now, key, f"archive/{key}", key),
        )
        conn.commit()
        return int(cur.rowcount or 0)
    finally:
        conn.close()


def enqueue_active_learning(
    detection_id: str,
    feedback_type: str = "low_confidence",
    proposed_class: str | None = None,
) -> dict[str, Any] | None:
    detection = get_detection(detection_id)
    if not detection:
        return None
    now = time.time()
    sample_id = str(uuid.uuid4())
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO active_learning_samples (
                id, detection_id, source_video, time_sec, feedback_type,
                proposed_class, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            ON CONFLICT(detection_id, feedback_type) DO UPDATE SET
                proposed_class = excluded.proposed_class,
                status = CASE
                    WHEN active_learning_samples.status = 'rejected' THEN 'pending'
                    ELSE active_learning_samples.status
                END,
                updated_at = excluded.updated_at
            """,
            (
                sample_id,
                detection_id,
                normalize_media_path(str(detection.get("source_video") or "")),
                float(detection.get("time_sec") or 0),
                feedback_type,
                proposed_class,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM active_learning_samples WHERE detection_id = ? AND feedback_type = ?",
            (detection_id, feedback_type),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_active_learning_samples(
    status: str = "pending",
    source_video: str | None = None,
) -> list[dict[str, Any]]:
    init_db()
    clauses = ["a.status = ?"]
    args: list[Any] = [status]
    if source_video:
        clauses.append("a.source_video = ?")
        args.append(normalize_media_path(source_video))
    conn = _connect()
    try:
        rows = conn.execute(
            f"""
            SELECT a.*, d.class_id, d.class_name, d.ai_class_name, d.confidence,
                   d.crop_path, d.is_deleted
            FROM active_learning_samples a
            JOIN detections d ON d.id = a.detection_id
            WHERE {' AND '.join(clauses)}
            ORDER BY a.created_at DESC
            """,
            args,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def decide_active_learning_sample(
    sample_id: str,
    status: str,
    *,
    proposed_class: str | None = None,
) -> dict[str, Any] | None:
    if status not in {"accepted", "rejected"}:
        raise ValueError("status must be accepted or rejected")
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE active_learning_samples
            SET status = ?, proposed_class = COALESCE(?, proposed_class), updated_at = ?
            WHERE id = ?
            """,
            (status, proposed_class, time.time(), sample_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM active_learning_samples WHERE id = ?",
            (sample_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_class_overrides() -> list[dict[str, Any]]:
    """All persisted class_overrides rows (may be empty)."""
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT class_id, name_ru, aliases, enabled, in_prompt,
                   confidence_threshold, updated_at
            FROM class_overrides
            ORDER BY class_id ASC
            """
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "class_id": int(row["class_id"]),
                    "name_ru": str(row["name_ru"] or ""),
                    "aliases": str(row["aliases"] or "[]"),
                    "enabled": bool(row["enabled"]),
                    "in_prompt": bool(row["in_prompt"]),
                    "confidence_threshold": (
                        float(row["confidence_threshold"])
                        if row["confidence_threshold"] is not None
                        else None
                    ),
                    "updated_at": float(row["updated_at"] or 0),
                }
            )
        return out
    finally:
        conn.close()


# COCO DROP classes — seed for excluded_classes table
_COCO_DROP_CLASSES: tuple[str, ...] = (
    "frisbee",
    "sports_ball",
    "sports ball",
    "dog",
    "cat",
    "horse",
    "sheep",
    "cow",
    "umbrella",
    "handbag",
    "suitcase",
    "skis",
    "snowboard",
    "skateboard",
    "surfboard",
    "tennis",
    "bottle",
    "cup",
    "chair",
    "bench",
    "tv",
    "laptop",
    "cell phone",
    "cell_phone",
    "keyboard",
    "mouse",
    "remote",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
    "stop sign",
    "parking meter",
    "traffic light",
    "fire hydrant",
    "potted plant",
    "dining table",
    "toilet",
    "sink",
    "refrigerator",
    "microwave",
    "oven",
    "toaster",
    "couch",
    "bed",
    "wine glass",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "tie",
    "backpack",
)


def _seed_excluded_classes() -> None:
    """Seed COCO DROP classes using INSERT OR IGNORE (idempotent)."""
    conn = _connect()
    try:
        for class_name in _COCO_DROP_CLASSES:
            conn.execute(
                "INSERT OR IGNORE INTO excluded_classes (class_name, added_at) VALUES (?, strftime('%s', 'now'))",
                (class_name,),
            )
        conn.commit()
    finally:
        conn.close()


def list_excluded_classes() -> list[dict[str, Any]]:
    """All excluded classes (COCO DROP + operator additions)."""
    init_db()
    _seed_excluded_classes()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT class_name, added_at
            FROM excluded_classes
            ORDER BY class_name ASC
            """
        ).fetchall()
        return [
            {
                "class_name": str(row["class_name"]),
                "added_at": float(row["added_at"]),
            }
            for row in rows
        ]
    finally:
        conn.close()


def upsert_excluded_class(class_name: str) -> dict[str, Any]:
    """Add or update an excluded class (idempotent)."""
    init_db()
    _seed_excluded_classes()
    class_name = class_name.strip().lower()
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO excluded_classes (class_name, added_at) VALUES (?, strftime('%s', 'now'))",
            (class_name,),
        )
        conn.commit()
        return {"class_name": class_name, "added_at": time.time()}
    finally:
        conn.close()


def delete_excluded_class(class_name: str) -> bool:
    """Remove a class from exclusion list. Returns True if deleted."""
    init_db()
    class_name = class_name.strip().lower()
    conn = _connect()
    try:
        cursor = conn.execute(
            "DELETE FROM excluded_classes WHERE class_name = ?",
            (class_name,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_class_override(class_id: int) -> dict[str, Any] | None:
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT class_id, name_ru, aliases, enabled, in_prompt,
                   confidence_threshold, updated_at
            FROM class_overrides WHERE class_id = ?
            """,
            (int(class_id),),
        ).fetchone()
        if row is None:
            return None
        return {
            "class_id": int(row["class_id"]),
            "name_ru": str(row["name_ru"] or ""),
            "aliases": str(row["aliases"] or "[]"),
            "enabled": bool(row["enabled"]),
            "in_prompt": bool(row["in_prompt"]),
            "confidence_threshold": (
                float(row["confidence_threshold"])
                if row["confidence_threshold"] is not None
                else None
            ),
            "updated_at": float(row["updated_at"] or 0),
        }
    finally:
        conn.close()


def upsert_class_override(
    class_id: int,
    *,
    name_ru: str | None = None,
    aliases: str | None = None,
    enabled: bool | None = None,
    in_prompt: bool | None = None,
    confidence_threshold: float | None = None,
    clear_confidence_threshold: bool = False,
) -> dict[str, Any]:
    """Create/update override. Unspecified fields keep previous or defaults."""
    init_db()
    prev = get_class_override(class_id)
    name_ru_v = name_ru if name_ru is not None else (prev["name_ru"] if prev else "")
    aliases_v = aliases if aliases is not None else (prev["aliases"] if prev else "[]")
    enabled_v = (
        (1 if enabled else 0)
        if enabled is not None
        else (1 if (prev["enabled"] if prev else True) else 0)
    )
    prompt_v = (
        (1 if in_prompt else 0)
        if in_prompt is not None
        else (1 if (prev["in_prompt"] if prev else False) else 0)
    )
    confidence_v = (
        None
        if clear_confidence_threshold
        else (
            float(confidence_threshold)
            if confidence_threshold is not None
            else (prev["confidence_threshold"] if prev else None)
        )
    )
    now = time.time()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO class_overrides (
                class_id, name_ru, aliases, enabled, in_prompt,
                confidence_threshold, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(class_id) DO UPDATE SET
                name_ru = excluded.name_ru,
                aliases = excluded.aliases,
                enabled = excluded.enabled,
                in_prompt = excluded.in_prompt,
                confidence_threshold = excluded.confidence_threshold,
                updated_at = excluded.updated_at
            """,
            (
                int(class_id),
                str(name_ru_v),
                str(aliases_v),
                enabled_v,
                prompt_v,
                confidence_v,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    row = get_class_override(class_id)
    assert row is not None
    return row


def delete_class_override(class_id: int) -> bool:
    init_db()
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM class_overrides WHERE class_id = ?", (int(class_id),))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def upsert_flight_track(
    video_path: str,
    track_data: list[dict[str, Any]] | str,
    source_file: str | None = None,
) -> dict[str, Any]:
    """Insert or replace flight track JSON for a video_path key."""
    init_db()
    path_key = str(video_path or "").strip()
    if not path_key:
        raise ValueError("video_path пуст")
    if isinstance(track_data, str):
        payload = track_data
        try:
            points = json.loads(track_data)
        except json.JSONDecodeError:
            points = []
    else:
        points = list(track_data)
        payload = json.dumps(points, ensure_ascii=False)
    now = time.time()
    track_id = str(uuid.uuid4())
    conn = _connect()
    try:
        prev = conn.execute(
            "SELECT id FROM flight_tracks WHERE video_path = ?", (path_key,)
        ).fetchone()
        if prev:
            track_id = str(prev["id"])
            conn.execute(
                """
                UPDATE flight_tracks
                SET track_data = ?, source_file = ?, created_at = ?
                WHERE video_path = ?
                """,
                (payload, source_file, now, path_key),
            )
        else:
            conn.execute(
                """
                INSERT INTO flight_tracks (id, video_path, track_data, source_file, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (track_id, path_key, payload, source_file, now),
            )
        conn.commit()
    finally:
        conn.close()
    return {
        "id": track_id,
        "video_path": path_key,
        "points": points if isinstance(points, list) else [],
        "source_file": source_file,
        "created_at": now,
        "point_count": len(points) if isinstance(points, list) else 0,
    }


def get_flight_track(video_path: str) -> dict[str, Any] | None:
    init_db()
    path_key = str(video_path or "").strip()
    if not path_key:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, video_path, track_data, source_file, created_at FROM flight_tracks WHERE video_path = ?",
            (path_key,),
        ).fetchone()
        if row is None:
            # Fallback: match by basename
            base = Path(path_key).name
            rows = conn.execute(
                "SELECT id, video_path, track_data, source_file, created_at FROM flight_tracks"
            ).fetchall()
            for cand in rows:
                if Path(str(cand["video_path"])).name == base:
                    row = cand
                    break
        if row is None:
            return None
        try:
            points = json.loads(row["track_data"] or "[]")
        except json.JSONDecodeError:
            points = []
        if not isinstance(points, list):
            points = []
        return {
            "id": row["id"],
            "video_path": row["video_path"],
            "points": points,
            "source_file": row["source_file"],
            "created_at": row["created_at"],
            "point_count": len(points),
        }
    finally:
        conn.close()


def get_embedding(detection_id: str) -> dict[str, Any] | None:
    init_db()
    det_id = str(detection_id or "")
    if not det_id:
        return None
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT detection_id, method, crop_mtime, dim, embedding, computed_at
            FROM detection_embeddings WHERE detection_id = ?
            """,
            (det_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "detection_id": row["detection_id"],
            "method": row["method"],
            "crop_mtime": float(row["crop_mtime"] or 0),
            "dim": int(row["dim"] or 0),
            "embedding": bytes(row["embedding"] or b""),
            "computed_at": float(row["computed_at"] or 0),
        }
    finally:
        conn.close()


def upsert_embedding(
    detection_id: str,
    method: str,
    crop_mtime: float,
    embedding: bytes,
    dim: int,
) -> None:
    init_db()
    det_id = str(detection_id or "")
    if not det_id:
        raise ValueError("detection_id пуст")
    blob = bytes(embedding or b"")
    now = time.time()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO detection_embeddings
                (detection_id, method, crop_mtime, dim, embedding, computed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(detection_id) DO UPDATE SET
                method = excluded.method,
                crop_mtime = excluded.crop_mtime,
                dim = excluded.dim,
                embedding = excluded.embedding,
                computed_at = excluded.computed_at
            """,
            (det_id, str(method), float(crop_mtime), int(dim), blob, now),
        )
        conn.commit()
    finally:
        conn.close()


def delete_embedding(detection_id: str) -> bool:
    init_db()
    det_id = str(detection_id or "")
    if not det_id:
        return False
    conn = _connect()
    try:
        cur = conn.execute(
            "DELETE FROM detection_embeddings WHERE detection_id = ?", (det_id,)
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ─── Schema versioning & migrations ─────────────────────────────────


def get_schema_version() -> int:
    """Get current database schema version."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'schema_version'"
        ).fetchone()
        return int(row["value"]) if row else 0
    finally:
        conn.close()


def migrate_db() -> None:
    """Run database migrations to ensure latest schema."""
    version = get_schema_version()
    conn = _connect()
    try:
        if version < 1:
            # Add excluded_classes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS excluded_classes (
                    class_name TEXT PRIMARY KEY,
                    added_at REAL NOT NULL DEFAULT 0
                )
            """)
            # Seed COCO DROP classes
            import time
            now = time.time()
            for class_name in _COCO_DROP_CLASSES:
                conn.execute(
                    "INSERT OR IGNORE INTO excluded_classes (class_name, added_at) VALUES (?, ?)",
                    (class_name, now),
                )
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('schema_version', '1')"
            )
            conn.commit()
            print("[DB] Migrated to schema v1 (excluded_classes table)")
        
        if version < 2:
            # Add batch_seg_jobs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS batch_seg_jobs (
                    task_id TEXT PRIMARY KEY,
                    video_path TEXT NOT NULL,
                    frame_step INTEGER NOT NULL DEFAULT 30,
                    confidence REAL NOT NULL DEFAULT 0.25,
                    status TEXT NOT NULL DEFAULT 'running',
                    last_frame_idx INTEGER NOT NULL DEFAULT 0,
                    total_frames INTEGER NOT NULL DEFAULT 0,
                    results_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute(
                "UPDATE settings SET value = '2' WHERE key = 'schema_version'"
            )
            conn.commit()
            print("[DB] Migrated to schema v2 (batch_seg_jobs table)")
        
        # Update version if we've made progress
        current_version = get_schema_version()
        if current_version < 2:
            conn.execute(
                "UPDATE settings SET value = ? WHERE key = 'schema_version'",
                (max(current_version, 2),),
            )
            conn.commit()
    finally:
        conn.close()


# ─── Batch segmentation checkpoint ─────────────────────────────────


def save_batch_seg_checkpoint(task_id: str, state: dict) -> None:
    """Save checkpoint for batch segmentation job."""
    init_db()
    conn = _connect()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO batch_seg_jobs (
                task_id, video_path, frame_step, confidence,
                status, last_frame_idx, total_frames,
                results_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
        """, (
            task_id,
            state["video_path"],
            state["frame_step"],
            state["confidence"],
            state["status"],
            state["last_frame_idx"],
            state["total_frames"],
            json.dumps(state.get("results", [])),
        ))
        conn.commit()
    finally:
        conn.close()


def load_batch_seg_checkpoint(task_id: str) -> dict | None:
    """Load checkpoint for batch segmentation job."""
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM batch_seg_jobs WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "task_id": row["task_id"],
            "video_path": row["video_path"],
            "frame_step": row["frame_step"],
            "confidence": row["confidence"],
            "status": row["status"],
            "last_frame_idx": row["last_frame_idx"],
            "total_frames": row["total_frames"],
            "results": json.loads(row["results_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    finally:
        conn.close()
