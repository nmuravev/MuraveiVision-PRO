"""Scan removable drives and import .pt / class YAML from USB (air-gapped)."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

from main import BASE_DIR
from services.classes import YAML_PATH, get_class_catalog, invalidate_class_cache

ASSETS_MODELS = BASE_DIR / "assets" / "models"
SKIP_DIR_NAMES = {
    "system volume information",
    "$recycle.bin",
    "recycler",
    ".trashes",
    "node_modules",
}
MAX_DEPTH = 2
MAX_FILES = 50
SETTING_TS = "usb_last_import_ts"
SETTING_PATH = "usb_last_import_path"

_extra_roots: list[Path] = []


def set_extra_scan_roots(paths: list[Path] | None) -> None:
    """Test hook: treat extra directories as removable roots."""
    global _extra_roots
    _extra_roots = [Path(p) for p in (paths or [])]


def extra_scan_roots() -> list[Path]:
    out = list(_extra_roots)
    raw = os.environ.get("MURAVEI_USB_EXTRA_ROOTS") or ""
    for part in raw.split(";"):
        p = part.strip().strip('"')
        if p:
            out.append(Path(p))
    return out


def list_removable_mounts() -> list[Path]:
    mounts: list[Path] = []
    if sys.platform == "win32":
        try:
            import ctypes

            GetDriveTypeW = ctypes.windll.kernel32.GetDriveTypeW
            GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
            GetDriveTypeW.restype = ctypes.c_uint
            DRIVE_REMOVABLE = 2
            for code in range(ord("A"), ord("Z") + 1):
                letter = chr(code)
                root = f"{letter}:\\"
                if GetDriveTypeW(root) == DRIVE_REMOVABLE:
                    p = Path(root)
                    if p.exists():
                        mounts.append(p)
        except Exception:  # noqa: BLE001
            pass
    try:
        import psutil

        for part in psutil.disk_partitions(all=False):
            opts = (part.opts or "").lower()
            if "removable" not in opts:
                continue
            p = Path(part.mountpoint)
            if p.exists() and p not in mounts:
                mounts.append(p)
    except Exception:  # noqa: BLE001
        pass
    for extra in extra_scan_roots():
        try:
            p = extra.resolve()
        except OSError:
            continue
        if p.is_dir() and p not in mounts:
            mounts.append(p)
    return mounts


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def assert_usb_source(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(str(resolved))
    roots = list_removable_mounts()
    if any(_is_under(resolved, r) for r in roots):
        return resolved
    raise PermissionError("source is not on a removable drive")


def _drive_label(root: Path) -> str:
    if sys.platform == "win32" and len(root.drive) == 2:
        try:
            import ctypes

            vol = ctypes.create_unicode_buffer(261)
            fs = ctypes.create_unicode_buffer(261)
            serial = ctypes.c_uint()
            maxlen = ctypes.c_uint()
            flags = ctypes.c_uint()
            ok = ctypes.windll.kernel32.GetVolumeInformationW(
                str(root.resolve()) + ("\\" if not str(root).endswith("\\") else ""),
                vol,
                261,
                ctypes.byref(serial),
                ctypes.byref(maxlen),
                ctypes.byref(flags),
                fs,
                261,
            )
            if ok and vol.value:
                return vol.value
        except Exception:  # noqa: BLE001
            pass
    return root.name or str(root)


def _iter_candidate_files(root: Path) -> list[Path]:
    found: list[Path] = []

    def walk(cur: Path, depth: int) -> None:
        if len(found) >= MAX_FILES:
            return
        try:
            entries = list(cur.iterdir())
        except OSError:
            return
        for ent in entries:
            if len(found) >= MAX_FILES:
                return
            try:
                if ent.is_dir():
                    if depth >= MAX_DEPTH:
                        continue
                    if ent.name.lower() in SKIP_DIR_NAMES:
                        continue
                    walk(ent, depth + 1)
                    continue
                suf = ent.suffix.lower()
                if suf in {".pt", ".yaml", ".yml"}:
                    found.append(ent)
            except OSError:
                continue

    walk(root, 0)
    return found


def _describe_file(path: Path) -> dict[str, Any]:
    from services.model_validator import validate_pt_file, validate_yaml_classes

    suf = path.suffix.lower()
    size_mb = round(path.stat().st_size / (1024 * 1024), 2)
    if suf == ".pt":
        meta = validate_pt_file(path)
        return {
            "path": str(path),
            "name": path.name,
            "type": "model",
            "size_mb": size_mb,
            "valid": bool(meta.get("valid")),
            "nc": meta.get("nc"),
            "count": None,
            "error": meta.get("error"),
        }
    meta = validate_yaml_classes(path)
    return {
        "path": str(path),
        "name": path.name,
        "type": "classes",
        "size_mb": size_mb,
        "valid": bool(meta.get("valid")),
        "nc": None,
        "count": meta.get("count"),
        "error": meta.get("error"),
    }


def scan_usb() -> dict[str, Any]:
    errors: list[str] = []
    drives: list[dict[str, Any]] = []
    try:
        mounts = list_removable_mounts()
    except Exception as exc:  # noqa: BLE001
        return {"drives": [], "errors": [f"scan failed: {exc}"]}
    if not mounts:
        errors.append("Съёмные диски не найдены")
    for root in mounts:
        letter = root.drive.rstrip("\\/") if root.drive else str(root)
        try:
            files = [_describe_file(p) for p in _iter_candidate_files(root)]
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{letter}: {exc}")
            files = []
        drives.append(
            {
                "letter": letter,
                "label": _drive_label(root),
                "mount": str(root),
                "files": files,
            }
        )
    return {"drives": drives, "errors": errors}


def _backup_if_exists(target: Path) -> Path | None:
    if not target.is_file():
        return None
    backup = target.with_name(target.name + ".backup")
    if backup.exists():
        backup.unlink()
    shutil.copy2(target, backup)
    return backup


def _model_dest(source: Path) -> Path:
    ASSETS_MODELS.mkdir(parents=True, exist_ok=True)
    name = source.name.lower()
    if "yoloe" in name:
        safe = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in source.name)
        return ASSETS_MODELS / safe
    return ASSETS_MODELS / "yolo26n-ft.pt"


def preview_import(source: Path, target_type: str) -> dict[str, Any]:
    from services.model_validator import validate_pt_file, validate_yaml_classes

    src = assert_usb_source(source)
    if target_type == "model":
        dest = _model_dest(src)
        meta = validate_pt_file(src)
        return {
            "dry_run": True,
            "source_path": str(src),
            "target_type": "model",
            "dest_path": str(dest),
            "backup_of": str(dest) if dest.is_file() else None,
            "valid": bool(meta.get("valid")),
            "nc": meta.get("nc"),
            "error": meta.get("error"),
            "message": f"Будет скопировано в {dest.name}" + (" (с .backup)" if dest.is_file() else ""),
        }
    dest = YAML_PATH
    meta = validate_yaml_classes(src)
    return {
        "dry_run": True,
        "source_path": str(src),
        "target_type": "classes",
        "dest_path": str(dest),
        "backup_of": str(dest) if dest.is_file() else None,
        "valid": bool(meta.get("valid")),
        "count": meta.get("count"),
        "error": meta.get("error"),
        "message": f"Будет заменён {dest.name}" + (" (с .backup)" if dest.is_file() else ""),
    }


def _stamp_import(path: Path) -> None:
    import time

    from services.db import set_setting

    set_setting(SETTING_TS, str(time.time()))
    set_setting(SETTING_PATH, str(path))


def confirm_import(source: Path, target_type: str) -> dict[str, Any]:
    from services.model_validator import validate_pt_file, validate_yaml_classes

    src = assert_usb_source(source)
    if target_type == "model":
        meta = validate_pt_file(src)
        if not meta.get("valid"):
            return {
                "success": False,
                "message": meta.get("error") or "invalid model",
                "new_model_path": None,
            }
        dest = _model_dest(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        backup = _backup_if_exists(dest)
        shutil.copy2(src, dest)
        check = validate_pt_file(dest)
        if not check.get("valid"):
            return {
                "success": False,
                "message": check.get("error") or "copied file failed validation",
                "new_model_path": str(dest),
                "backup_path": str(backup) if backup else None,
            }
        loaded = False
        load_error = None
        try:
            from services.yolo_engine import get_yolo_engine

            loaded = bool(get_yolo_engine().force_load(dest))
            if not loaded:
                load_error = "force_load returned False"
        except Exception as exc:  # noqa: BLE001
            load_error = str(exc)
        _stamp_import(dest)
        msg = f"Модель установлена: {dest.name}"
        if backup:
            msg += f"; backup {backup.name}"
        if not loaded:
            msg += f" (hot-swap: {load_error or 'не загружена'}; перезапуск подхватит yolo26n-ft.pt)"
        return {
            "success": True,
            "message": msg,
            "new_model_path": str(dest),
            "backup_path": str(backup) if backup else None,
            "hot_swap": loaded,
        }

    meta = validate_yaml_classes(src)
    if not meta.get("valid"):
        return {
            "success": False,
            "message": meta.get("error") or "invalid yaml",
            "new_model_path": None,
        }
    dest = YAML_PATH
    backup = _backup_if_exists(dest)
    shutil.copy2(src, dest)
    check = validate_yaml_classes(dest)
    if not check.get("valid"):
        return {
            "success": False,
            "message": check.get("error") or "copied yaml failed validation",
            "new_model_path": str(dest),
        }
    invalidate_class_cache()
    catalog = get_class_catalog()
    try:
        from services.response_validator import get_validator

        get_validator().refresh_catalog()
    except Exception:  # noqa: BLE001
        pass
    _stamp_import(dest)
    msg = f"Словарь классов обновлён ({check.get('count')} имён, catalog={len(catalog)})"
    if backup:
        msg += f"; backup {backup.name}"
    return {
        "success": True,
        "message": msg,
        "new_model_path": str(dest),
        "backup_path": str(backup) if backup else None,
        "classes_count": len(catalog),
    }


def last_import_info() -> dict[str, Any]:
    from services.db import get_setting

    ts_raw = get_setting(SETTING_TS)
    try:
        ts = float(ts_raw) if ts_raw else None
    except (TypeError, ValueError):
        ts = None
    return {"last_import": ts, "last_import_path": get_setting(SETTING_PATH)}
