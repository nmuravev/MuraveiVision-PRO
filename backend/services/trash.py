"""Soft-delete for archive media → archive/.trash/."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from services.security import archive_root, assert_in_archive, safe_path_resolve

TRASH_MAX_AGE_SEC = 30 * 24 * 3600


def trash_root() -> Path:
    root = archive_root() / ".trash"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _assert_under_archive(path: Path) -> Path:
    target = safe_path_resolve(path)
    root = archive_root()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Path outside archive") from exc
    return target


def move_to_trash(path: str | Path) -> dict[str, Any]:
    target = assert_in_archive(path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")
    if target.is_dir():
        raise HTTPException(status_code=400, detail="Папки через этот API не удаляются")
    trash = trash_root()
    try:
        target.relative_to(trash)
        raise HTTPException(status_code=400, detail="Файл уже в корзине")
    except ValueError:
        pass
    except HTTPException:
        raise

    ts = int(time.time())
    dest_name = f"{target.name}.{ts}"
    dest = trash / dest_name
    # avoid collision
    n = 0
    while dest.exists():
        n += 1
        dest = trash / f"{target.name}.{ts}_{n}"
        dest_name = dest.name

    meta = {
        "original": str(target),
        "name": target.name,
        "deleted_at": ts,
        "trash_name": dest_name,
    }
    shutil.move(str(target), str(dest))
    (trash / f"{dest_name}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"ok": True, "trash_path": str(dest), "original": str(target), "meta": meta}


def list_trash() -> list[dict[str, Any]]:
    trash = trash_root()
    items: list[dict[str, Any]] = []
    for meta_file in sorted(trash.glob("*.meta.json"), reverse=True):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        trash_name = str(meta.get("trash_name") or meta_file.name.replace(".meta.json", ""))
        trash_path = trash / trash_name
        if not trash_path.is_file():
            continue
        items.append(
            {
                "name": meta.get("name") or trash_path.name,
                "original": meta.get("original"),
                "trash_path": str(trash_path),
                "deleted_at": meta.get("deleted_at"),
                "size": trash_path.stat().st_size,
            }
        )
    return items


def restore_from_trash(trash_path: str | Path) -> dict[str, Any]:
    trash = trash_root()
    item = _assert_under_archive(trash_path)
    try:
        item.relative_to(trash)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Путь не в корзине") from exc
    if not item.is_file():
        raise HTTPException(status_code=404, detail="Файл в корзине не найден")

    meta_file = trash / f"{item.name}.meta.json"
    original: Path | None = None
    if meta_file.is_file():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            original = Path(str(meta.get("original") or ""))
        except Exception:  # noqa: BLE001
            original = None
    if original is None or not str(original):
        # fallback: archive root / original basename without timestamp suffix
        name = item.name
        # strip .timestamp
        parts = name.rsplit(".", 1)
        base = parts[0] if len(parts) == 2 and parts[1].isdigit() else name
        original = archive_root() / base

    original = _assert_under_archive(original)
    original.parent.mkdir(parents=True, exist_ok=True)
    if original.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Целевой файл уже существует: {original.name}",
        )
    shutil.move(str(item), str(original))
    if meta_file.is_file():
        meta_file.unlink(missing_ok=True)
    return {"ok": True, "restored": str(original)}


def permanent_delete(trash_path: str | Path) -> dict[str, Any]:
    trash = trash_root()
    item = _assert_under_archive(trash_path)
    try:
        item.relative_to(trash)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Путь не в корзине") from exc
    if not item.exists():
        raise HTTPException(status_code=404, detail="Не найдено")
    if item.is_dir():
        raise HTTPException(status_code=400, detail="Нельзя удалить папку")
    meta_file = trash / f"{item.name}.meta.json"
    item.unlink(missing_ok=True)
    if meta_file.is_file():
        meta_file.unlink(missing_ok=True)
    return {"ok": True}


def purge_old_trash(max_age_sec: int = TRASH_MAX_AGE_SEC) -> int:
    """Remove trash entries older than max_age_sec. Returns count removed."""
    trash = trash_root()
    now = time.time()
    removed = 0
    for meta_file in list(trash.glob("*.meta.json")):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            deleted_at = float(meta.get("deleted_at") or 0)
        except Exception:  # noqa: BLE001
            continue
        if deleted_at and (now - deleted_at) < max_age_sec:
            continue
        trash_name = str(meta.get("trash_name") or meta_file.name.replace(".meta.json", ""))
        item = trash / trash_name
        try:
            if item.is_file():
                item.unlink()
            meta_file.unlink(missing_ok=True)
            removed += 1
        except OSError:
            continue
    return removed
