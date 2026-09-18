"""Chunked network chat attachments under archive/network_attachments/."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any

from config import BASE_DIR

MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
CHUNK_SIZE = 256 * 1024
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)

_ATTACH_ID_RE = re.compile(r"^[a-f0-9]{8,64}$", re.IGNORECASE)


def attachments_root() -> Path:
    root = BASE_DIR / "archive" / "network_attachments"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_id(attachment_id: str) -> str:
    aid = (attachment_id or "").strip().lower()
    if not _ATTACH_ID_RE.match(aid):
        raise ValueError("invalid attachment_id")
    return aid


def attachment_dir(attachment_id: str) -> Path:
    return attachments_root() / _safe_id(attachment_id)


def meta_path(attachment_id: str) -> Path:
    return attachment_dir(attachment_id) / "meta.json"


def blob_path(attachment_id: str) -> Path:
    return attachment_dir(attachment_id) / "blob"


def chunk_path(attachment_id: str, index: int) -> Path:
    chunks = attachment_dir(attachment_id) / "chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    return chunks / f"{int(index)}.bin"


def read_meta(attachment_id: str) -> dict[str, Any] | None:
    path = meta_path(attachment_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_meta(attachment_id: str, meta: dict[str, Any]) -> None:
    d = attachment_dir(attachment_id)
    d.mkdir(parents=True, exist_ok=True)
    meta_path(attachment_id).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_complete(attachment_id: str) -> bool:
    meta = read_meta(attachment_id)
    if not meta or not meta.get("complete"):
        return False
    return blob_path(attachment_id).is_file()


def init_attachment(
    *,
    filename: str,
    content_type: str,
    size: int,
    sha256: str,
    attachment_id: str | None = None,
) -> dict[str, Any]:
    # P1-6: Sanitize filename to prevent path traversal
    safe_name = Path(filename).name  # Extract basename only
    if not safe_name or "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError("invalid filename (path traversal detected)")
    size_n = int(size)
    if size_n <= 0 or size_n > MAX_ATTACHMENT_BYTES:
        raise ValueError(f"size must be 1..{MAX_ATTACHMENT_BYTES}")
    ctype = (content_type or "").strip().lower() or "application/octet-stream"
    if ctype not in ALLOWED_CONTENT_TYPES:
        raise ValueError("unsupported content_type")
    digest = (sha256 or "").strip().lower()
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("sha256 must be 64 hex chars")
    name = safe_name[:200] or "attach.bin"
    aid = _safe_id(attachment_id) if attachment_id else uuid.uuid4().hex
    existing = read_meta(aid)
    if existing and existing.get("complete") and existing.get("sha256") == digest:
        return existing
    total_chunks = (size_n + CHUNK_SIZE - 1) // CHUNK_SIZE
    meta = {
        "id": aid,
        "filename": name,
        "content_type": ctype,
        "size": size_n,
        "sha256": digest,
        "chunk_size": CHUNK_SIZE,
        "total_chunks": total_chunks,
        "complete": False,
    }
    write_meta(aid, meta)
    return meta


def put_chunk(attachment_id: str, index: int, data: bytes) -> dict[str, Any]:
    meta = read_meta(attachment_id)
    if meta is None:
        raise FileNotFoundError("attachment not found")
    if meta.get("complete"):
        return meta
    idx = int(index)
    total = int(meta.get("total_chunks") or 0)
    if idx < 0 or idx >= total:
        raise ValueError("chunk index out of range")
    expected = int(meta.get("chunk_size") or CHUNK_SIZE)
    size = int(meta.get("size") or 0)
    if idx == total - 1:
        expected = size - idx * int(meta.get("chunk_size") or CHUNK_SIZE)
    if len(data) != expected:
        raise ValueError(f"chunk size mismatch: got {len(data)} expected {expected}")
    chunk_path(attachment_id, idx).write_bytes(data)
    return meta


def finalize_attachment(attachment_id: str) -> dict[str, Any]:
    meta = read_meta(attachment_id)
    if meta is None:
        raise FileNotFoundError("attachment not found")
    if meta.get("complete") and blob_path(attachment_id).is_file():
        return meta
    total = int(meta.get("total_chunks") or 0)
    expected_sha = str(meta.get("sha256") or "").lower()
    hasher = hashlib.sha256()
    parts: list[bytes] = []
    for i in range(total):
        p = chunk_path(attachment_id, i)
        if not p.is_file():
            raise ValueError(f"missing chunk {i}")
        raw = p.read_bytes()
        hasher.update(raw)
        parts.append(raw)
    digest = hasher.hexdigest()
    if digest != expected_sha:
        raise ValueError("sha256 mismatch")
    blob = b"".join(parts)
    if len(blob) != int(meta.get("size") or 0):
        raise ValueError("size mismatch after reassembly")
    blob_path(attachment_id).write_bytes(blob)
    meta["complete"] = True
    write_meta(attachment_id, meta)
    # Drop chunk files to save space
    chunks_dir = attachment_dir(attachment_id) / "chunks"
    if chunks_dir.is_dir():
        for child in chunks_dir.iterdir():
            try:
                child.unlink()
            except OSError:
                pass
    return meta


def read_blob(attachment_id: str) -> tuple[bytes, dict[str, Any]]:
    meta = read_meta(attachment_id)
    if meta is None or not meta.get("complete"):
        raise FileNotFoundError("attachment not ready")
    path = blob_path(attachment_id)
    if not path.is_file():
        raise FileNotFoundError("blob missing")
    return path.read_bytes(), meta


def read_chunk_bytes(attachment_id: str, index: int) -> bytes:
    """Return chunk bytes from staging or from assembled blob."""
    meta = read_meta(attachment_id)
    if meta is None:
        raise FileNotFoundError("attachment not found")
    idx = int(index)
    total = int(meta.get("total_chunks") or 0)
    if idx < 0 or idx >= total:
        raise ValueError("chunk index out of range")
    staged = chunk_path(attachment_id, idx)
    if staged.is_file():
        return staged.read_bytes()
    if not meta.get("complete"):
        raise FileNotFoundError(f"chunk {idx} missing")
    data, _ = read_blob(attachment_id)
    cs = int(meta.get("chunk_size") or CHUNK_SIZE)
    start = idx * cs
    end = min(len(data), start + cs)
    return data[start:end]
