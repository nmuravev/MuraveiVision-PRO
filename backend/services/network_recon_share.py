"""Chunked recon package share (sparse/dense/mesh/splat) between network bases."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from config import BASE_DIR
from services.job_ids import sanitize_job_id

CHUNK_SIZE = 1024 * 1024  # 1 MiB
MAX_ARTIFACT_BYTES = 1024 * 1024 * 1024  # 1 GiB per artifact
ARTIFACT_KINDS = ("sparse", "dense", "mesh", "splat")
_PKG_ID_RE = re.compile(r"^[a-f0-9]{8,64}$", re.IGNORECASE)


def packages_root() -> Path:
    root = BASE_DIR / "archive" / "network_recon_packages"
    root.mkdir(parents=True, exist_ok=True)
    return root


def recon_root() -> Path:
    root = BASE_DIR / "archive" / "recon"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_pkg(package_id: str) -> str:
    pid = (package_id or "").strip().lower()
    if not _PKG_ID_RE.match(pid):
        raise ValueError("invalid package_id")
    return pid


def package_dir(package_id: str) -> Path:
    return packages_root() / _safe_pkg(package_id)


def manifest_path(package_id: str) -> Path:
    return package_dir(package_id) / "manifest.json"


def artifact_dir(package_id: str, kind: str) -> Path:
    return package_dir(package_id) / "artifacts" / kind


def read_manifest(package_id: str) -> dict[str, Any] | None:
    path = manifest_path(package_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_manifest(package_id: str, man: dict[str, Any]) -> None:
    d = package_dir(package_id)
    d.mkdir(parents=True, exist_ok=True)
    manifest_path(package_id).write_text(
        json.dumps(man, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def free_bytes(path: Path | None = None) -> int:
    target = path or BASE_DIR / "archive"
    target.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(str(target))
    return int(usage.free)


def disk_preflight(needed_bytes: int, *, margin: float = 1.1) -> dict[str, Any]:
    free = free_bytes()
    need = int(max(0, needed_bytes) * margin)
    ok = free >= need
    return {
        "ok": ok,
        "free_bytes": free,
        "needed_bytes": need,
        "message": None if ok else "Недостаточно места на диске для приёма пакета 3D",
    }


def _job_dir(job_id: str) -> Path:
    jid = sanitize_job_id(job_id)
    d = recon_root() / jid
    if not d.is_dir():
        raise FileNotFoundError(f"job not found: {jid}")
    return d


def _load_job_manifest(job_dir: Path) -> dict[str, Any]:
    path = job_dir / "manifest.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_artifact_file(job_dir: Path, kind: str) -> Path | None:
    """Return path to primary file for kind, or None if missing."""
    kind = kind.strip().lower()
    if kind not in ARTIFACT_KINDS:
        return None
    man = _load_job_manifest(job_dir)
    arts = man.get("artifacts") or {}
    entry = arts.get(kind) if isinstance(arts, dict) else None
    if isinstance(entry, dict) and entry.get("file"):
        p = job_dir / str(entry["file"])
        if p.is_file():
            return p
    if isinstance(entry, str) and entry:
        p = job_dir / entry
        if p.is_file():
            return p
    fallbacks = {
        "sparse": [man.get("sparse_file") or "sparse_points.json", "preview.ply"],
        "dense": ["dense.ply", "dense_point_cloud.ply"],
        "mesh": ["textured_mesh.obj", "mesh.obj"],
        "splat": ["model.ply", "point_cloud.ply"],
    }
    for name in fallbacks.get(kind, []):
        if not name:
            continue
        p = job_dir / str(name)
        if p.is_file():
            return p
    # COLMAP sparse dir as zip-able marker — use sparse_points.json only for N4
    return None


def list_offerable_artifacts(job_id: str) -> dict[str, Any]:
    job_dir = _job_dir(job_id)
    out: dict[str, Any] = {}
    for kind in ARTIFACT_KINDS:
        path = resolve_artifact_file(job_dir, kind)
        if path is None:
            continue
        size = path.stat().st_size
        if size <= 0 or size > MAX_ARTIFACT_BYTES:
            continue
        out[kind] = {
            "file": path.name,
            "relpath": str(path.relative_to(job_dir)).replace("\\", "/"),
            "size": size,
        }
    return {"job_id": sanitize_job_id(job_id), "artifacts": out}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def create_offer(
    *,
    job_id: str,
    kinds: list[str],
    package_id: str | None = None,
    source_base: str | None = None,
) -> dict[str, Any]:
    job_dir = _job_dir(job_id)
    selected = [k.strip().lower() for k in kinds if k.strip().lower() in ARTIFACT_KINDS]
    if not selected:
        raise ValueError("no artifacts selected")
    offerable = list_offerable_artifacts(job_id)["artifacts"]
    missing = [k for k in selected if k not in offerable]
    if missing:
        raise ValueError(f"artifacts missing: {', '.join(missing)}")
    pid = _safe_pkg(package_id) if package_id else uuid.uuid4().hex
    arts: dict[str, Any] = {}
    for kind in selected:
        src = resolve_artifact_file(job_dir, kind)
        assert src is not None
        size = src.stat().st_size
        digest = _sha256_file(src)
        total = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
        ad = artifact_dir(pid, kind)
        ad.mkdir(parents=True, exist_ok=True)
        blob = ad / "blob"
        shutil.copy2(src, blob)
        arts[kind] = {
            "file": src.name,
            "relpath": offerable[kind]["relpath"],
            "size": size,
            "sha256": digest,
            "chunk_size": CHUNK_SIZE,
            "total_chunks": total,
            "complete": True,
            "staged": True,
        }
    man = {
        "id": pid,
        "job_id": sanitize_job_id(job_id),
        "source_base": (source_base or "").strip() or None,
        "artifacts": arts,
        "direction": "out",
        "complete": True,
    }
    write_manifest(pid, man)
    return man


def init_receive(
    *,
    package_id: str,
    job_id: str,
    artifacts: dict[str, Any],
    source_base: str | None = None,
    selected: list[str] | None = None,
) -> dict[str, Any]:
    """Prepare inbound package meta (chunks not yet present)."""
    pid = _safe_pkg(package_id)
    jid = sanitize_job_id(job_id)
    want = selected or list(artifacts.keys())
    want = [k for k in want if k in ARTIFACT_KINDS and k in artifacts]
    if not want:
        raise ValueError("no artifacts selected")
    needed = sum(int((artifacts[k] or {}).get("size") or 0) for k in want)
    pre = disk_preflight(needed)
    if not pre["ok"]:
        raise OSError(pre["message"] or "disk full")
    arts: dict[str, Any] = {}
    for kind in want:
        meta = dict(artifacts[kind] or {})
        size = int(meta.get("size") or 0)
        if size <= 0 or size > MAX_ARTIFACT_BYTES:
            raise ValueError(f"bad size for {kind}")
        digest = str(meta.get("sha256") or "").lower()
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError(f"bad sha256 for {kind}")
        cs = int(meta.get("chunk_size") or CHUNK_SIZE)
        total = int(meta.get("total_chunks") or ((size + cs - 1) // cs))
        arts[kind] = {
            "file": Path(str(meta.get("file") or f"{kind}.bin")).name,
            "relpath": str(meta.get("relpath") or meta.get("file") or f"{kind}.bin"),
            "size": size,
            "sha256": digest,
            "chunk_size": cs,
            "total_chunks": total,
            "complete": False,
            "received_chunks": 0,
        }
        artifact_dir(pid, kind).mkdir(parents=True, exist_ok=True)
    man = {
        "id": pid,
        "job_id": jid,
        "source_base": (source_base or "").strip() or None,
        "artifacts": arts,
        "direction": "in",
        "complete": False,
        "selected": want,
    }
    write_manifest(pid, man)
    return man


def put_chunk(package_id: str, kind: str, index: int, data: bytes) -> dict[str, Any]:
    man = read_manifest(package_id)
    if man is None:
        raise FileNotFoundError("package not found")
    kind = kind.strip().lower()
    art = (man.get("artifacts") or {}).get(kind)
    if not isinstance(art, dict):
        raise ValueError("unknown artifact kind")
    if art.get("complete"):
        return man
    idx = int(index)
    total = int(art.get("total_chunks") or 0)
    if idx < 0 or idx >= total:
        raise ValueError("chunk index out of range")
    cs = int(art.get("chunk_size") or CHUNK_SIZE)
    size = int(art.get("size") or 0)
    expected = size - idx * cs if idx == total - 1 else cs
    if len(data) != expected:
        raise ValueError(f"chunk size mismatch: got {len(data)} expected {expected}")
    chunks = artifact_dir(package_id, kind) / "chunks"
    chunks.mkdir(parents=True, exist_ok=True)
    (chunks / f"{idx}.bin").write_bytes(data)
    # Count present chunks for resume UI
    present = sum(1 for i in range(total) if (chunks / f"{i}.bin").is_file())
    art["received_chunks"] = present
    man["artifacts"][kind] = art
    write_manifest(package_id, man)
    return man


def next_missing_chunk(package_id: str, kind: str) -> int | None:
    man = read_manifest(package_id)
    if man is None:
        return None
    art = (man.get("artifacts") or {}).get(kind)
    if not isinstance(art, dict) or art.get("complete"):
        return None
    total = int(art.get("total_chunks") or 0)
    chunks = artifact_dir(package_id, kind) / "chunks"
    for i in range(total):
        if not (chunks / f"{i}.bin").is_file():
            return i
    return None


def finalize_artifact(package_id: str, kind: str) -> dict[str, Any]:
    man = read_manifest(package_id)
    if man is None:
        raise FileNotFoundError("package not found")
    kind = kind.strip().lower()
    art = (man.get("artifacts") or {}).get(kind)
    if not isinstance(art, dict):
        raise ValueError("unknown artifact")
    ad = artifact_dir(package_id, kind)
    blob = ad / "blob"
    if art.get("complete") and blob.is_file():
        return man
    total = int(art.get("total_chunks") or 0)
    cs = int(art.get("chunk_size") or CHUNK_SIZE)
    expected_sha = str(art.get("sha256") or "").lower()
    hasher = hashlib.sha256()
    parts: list[bytes] = []
    for i in range(total):
        p = ad / "chunks" / f"{i}.bin"
        if not p.is_file():
            raise ValueError(f"missing chunk {i}")
        raw = p.read_bytes()
        hasher.update(raw)
        parts.append(raw)
    digest = hasher.hexdigest()
    if digest != expected_sha:
        raise ValueError("sha256 mismatch")
    data = b"".join(parts)
    if len(data) != int(art.get("size") or 0):
        raise ValueError("size mismatch")
    blob.write_bytes(data)
    art["complete"] = True
    art["received_chunks"] = total
    man["artifacts"][kind] = art
    # cleanup chunks
    cdir = ad / "chunks"
    if cdir.is_dir():
        for child in cdir.iterdir():
            try:
                child.unlink()
            except OSError:
                pass
    all_done = all(
        isinstance(a, dict) and a.get("complete")
        for a in (man.get("artifacts") or {}).values()
    )
    man["complete"] = all_done
    write_manifest(package_id, man)
    return man


def read_chunk_bytes(package_id: str, kind: str, index: int) -> bytes:
    man = read_manifest(package_id)
    if man is None:
        raise FileNotFoundError("package not found")
    art = (man.get("artifacts") or {}).get(kind)
    if not isinstance(art, dict):
        raise ValueError("unknown artifact")
    idx = int(index)
    total = int(art.get("total_chunks") or 0)
    if idx < 0 or idx >= total:
        raise ValueError("chunk index out of range")
    staged = artifact_dir(package_id, kind) / "chunks" / f"{idx}.bin"
    if staged.is_file():
        return staged.read_bytes()
    blob = artifact_dir(package_id, kind) / "blob"
    if not blob.is_file():
        raise FileNotFoundError(f"chunk {idx} missing")
    cs = int(art.get("chunk_size") or CHUNK_SIZE)
    data = blob.read_bytes()
    start = idx * cs
    end = min(len(data), start + cs)
    return data[start:end]


def unpack_to_recon(package_id: str) -> dict[str, Any]:
    """Copy completed blobs into archive/recon/<job_id>/ and patch manifest."""
    man = read_manifest(package_id)
    if man is None:
        raise FileNotFoundError("package not found")
    if not man.get("complete"):
        raise ValueError("package incomplete")
    jid = sanitize_job_id(str(man.get("job_id") or ""))
    job_dir = recon_root() / jid
    job_dir.mkdir(parents=True, exist_ok=True)
    job_man = _load_job_manifest(job_dir)
    arts = job_man.setdefault("artifacts", {})
    if not isinstance(arts, dict):
        arts = {}
        job_man["artifacts"] = arts
    unpacked: list[str] = []
    for kind, art in (man.get("artifacts") or {}).items():
        if not isinstance(art, dict) or not art.get("complete"):
            continue
        blob = artifact_dir(package_id, kind) / "blob"
        if not blob.is_file():
            continue
        rel = str(art.get("relpath") or art.get("file") or f"{kind}.bin")
        dest = job_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(blob, dest)
        arts[kind] = {"file": Path(rel).name if "/" not in rel.replace("\\", "/") else rel}
        # keep simple file name in artifacts entry
        arts[kind] = {"file": str(art.get("file") or dest.name)}
        unpacked.append(kind)
    job_man["job_id"] = jid
    job_man["status"] = job_man.get("status") or "imported_network"
    job_man["network_package_id"] = _safe_pkg(package_id)
    (job_dir / "manifest.json").write_text(
        json.dumps(job_man, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"job_id": jid, "unpacked": unpacked, "job_dir": str(job_dir)}
