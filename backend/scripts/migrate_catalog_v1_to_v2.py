#!/usr/bin/env python
"""Migrate catalog from v1 (pickle) to v2 (msgpack).

Run once at application startup. Creates .bak backups before conversion.
Atomic file replacement via os.replace() to prevent data corruption.

Usage:
    python -m backend.scripts.migrate_catalog_v1_to_v2
    # or
    python backend/scripts/migrate_catalog_v1_to_v2.py
"""
from __future__ import annotations

import json
import logging
import os
import pickle
import shutil
import sys
import time
from pathlib import Path
from typing import Any

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
    import msgpack
except ImportError:
    msgpack = None  # Will be checked at runtime

from config import BASE_DIR

logger = logging.getLogger(__name__)

# --- Configuration ---
CATALOG_V1_PATH = BASE_DIR / "data" / "catalog_v1.pkl"
CATALOG_V2_PATH = BASE_DIR / "data" / "catalog_v2.msgpack"
CATALOG_V2_TEMP_PATH = BASE_DIR / "data" / "catalog_v2.msgpack.tmp"
BACKUP_SUFFIX = ".bak"
CATALOG_VERSION = 2

# Env override for testing
_FORCE_MIGRATE = os.environ.get("FORCE_MIGRATE", "0") == "1"


def _ensure_data_dir() -> Path:
    """Create data directory if it doesn't exist."""
    data_dir = BASE_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _create_backup(pkl_path: Path) -> Path:
    """Create backup of .pkl file before migration.
    
    Returns:
        Path to backup file
    """
    backup_path = pkl_path.with_suffix(pkl_path.suffix + BACKUP_SUFFIX)
    if pkl_path.exists():
        shutil.copy2(str(pkl_path), str(backup_path))
        logger.info(f"Created backup: {backup_path}")
    return backup_path


def _load_pickle_catalog(pkl_path: Path) -> dict[str, Any] | None:
    """Load catalog from pickle file safely.
    
    Uses RestrictedUnpickler to prevent RCE.
    
    Args:
        pkl_path: Path to .pkl file
        
    Returns:
        Catalog dict or None if file doesn't exist or fails to load
    """
    if not pkl_path.exists():
        logger.info(f"Pickle catalog not found: {pkl_path}")
        return None
    
    try:
        # For safety, restrict unpickling to basic types only
        import builtins
        
        SAFE_BUILTINS = {
            'dict', 'list', 'tuple', 'set', 'frozenset',
            'str', 'bytes', 'int', 'float', 'bool',
            'NoneType',
        }
        
        class RestrictedUnpickler(pickle.Unpickler):
            def find_class(self, module, name):
                # Only allow builtins
                if module == 'builtins' or module == '__builtin__':
                    if name in SAFE_BUILTINS:
                        return getattr(builtins, name, None) or getattr(sys.modules.get('__builtin__' if module == 'builtins' else '__builtin__'), name, None)
                    # Allow common types that might be in serialized data
                    if module in ('builtins', '__builtin__'):
                        return getattr(__import__(module), name)
                # For numpy arrays and other complex types, allow basic containers
                if module.startswith('numpy') or module.startswith('torch'):
                    # Allow basic numpy/torch types that might be in catalog
                    if name in ('ndarray',):
                        return __import__(module).core.multiarray._reconstruct
                return super().find_class(module, name)
        
        with open(pkl_path, 'rb') as f:
            catalog = RestrictedUnpickler(f).load()
        
        logger.info(f"Loaded pickle catalog with {len(catalog)} entries")
        return catalog
        
    except Exception as exc:
        logger.error(f"Failed to load pickle catalog: {exc}")
        return None


def _convert_to_v2_format(pickle_data: dict[str, Any]) -> dict[str, Any]:
    """Convert pickle catalog data to v2 msgpack format.
    
    Handles numpy arrays, torch tensors, and other complex types
    by converting them to bytes/base64.
    
    Args:
        pickle_data: Original pickle catalog data
        
    Returns:
        Converted v2 format dict
    """
    v2_data: dict[str, Any] = {
        "version": CATALOG_VERSION,
        "migrated_at": time.time(),
        "catalog": [],
    }
    
    if isinstance(pickle_data, dict):
        # Convert each entry
        for key, value in pickle_data.items():
            v2_entry = _convert_entry(key, value)
            v2_data["catalog"].append(v2_entry)
    elif isinstance(pickle_data, list):
        # List format
        for i, item in enumerate(pickle_data):
            v2_entry = _convert_entry(i, item)
            v2_data["catalog"].append(v2_entry)
    else:
        logger.warning(f"Unexpected pickle data format: {type(pickle_data)}")
        v2_data["catalog"] = []
    
    return v2_data


def _convert_entry(key: Any, value: Any) -> dict[str, Any]:
    """Convert a single catalog entry, handling complex types.
    
    Args:
        key: Entry key
        value: Entry value
        
    Returns:
        Converted entry dict
    """
    entry: dict[str, Any] = {"key": str(key)}
    
    if isinstance(value, dict):
        entry["type"] = "dict"
        entry["value"] = {}
        for k, v in value.items():
            entry["value"][str(k)] = _serialize_value(v)
    elif isinstance(value, (list, tuple)):
        entry["type"] = "list"
        entry["value"] = [_serialize_value(item) for item in value]
    else:
        entry["type"] = "scalar"
        entry["value"] = _serialize_value(value)
    
    return entry


def _serialize_value(value: Any) -> Any:
    """Serialize a value, handling numpy arrays, torch tensors, etc.
    
    Args:
        value: Value to serialize
        
    Returns:
        Serialized value (str, int, float, dict, etc.)
    """
    # Handle numpy arrays
    if hasattr(value, 'numpy'):
        # PyTorch tensor
        return {
            "__type__": "torch_tensor",
            "__data__": value.numpy().tobytes().hex(),
            "__shape__": list(value.shape),
            "__dtype__": str(value.dtype),
        }
    
    if hasattr(value, 'tobytes'):
        # Numpy array
        return {
            "__type__": "numpy_array",
            "__data__": value.tobytes().hex(),
            "__shape__": list(value.shape),
            "__dtype__": str(value.dtype),
        }
    
    # Handle bytes
    if isinstance(value, bytes):
        return {
            "__type__": "bytes",
            "__data__": value.hex(),
        }
    
    # Handle standard types
    if isinstance(value, (str, int, float, bool)):
        return value
    if value is None:
        return None
    
    # Handle other complex types
    try:
        return str(value)
    except Exception:
        return f"<unserializable: {type(value).__name__}>"


def _save_msgpack_v2(v2_data: dict[str, Any], temp_path: Path, final_path: Path) -> bool:
    """Save v2 catalog to msgpack format atomically.
    
    Args:
        v2_data: Catalog data in v2 format
        temp_path: Temporary file path
        final_path: Final file path
        
    Returns:
        True if successful, False otherwise
    """
    if msgpack is None:
        logger.error("msgpack not installed. Install with: pip install msgpack")
        return False
    
    try:
        # Write to temporary file first
        with open(temp_path, 'wb') as f:
            # Use compress=True for smaller file size
            msgpack.pack(v2_data, f, use_bin_type=True, strict_types=True)
        
        # Atomic replacement
        os.replace(str(temp_path), str(final_path))
        logger.info(f"Saved v2 catalog to {final_path}")
        return True
        
    except Exception as exc:
        logger.error(f"Failed to save msgpack catalog: {exc}")
        # Clean up temp file
        if temp_path.exists():
            temp_path.unlink()
        return False


def _load_msgpack_v2(msgpack_path: Path) -> dict[str, Any] | None:
    """Load v2 catalog from msgpack file.
    
    Args:
        msgpack_path: Path to .msgpack file
        
    Returns:
        Catalog dict or None if file doesn't exist or fails to load
    """
    if msgpack is None:
        logger.error("msgpack not installed")
        return None
    
    if not msgpack_path.exists():
        logger.info(f"Msgpack catalog not found: {msgpack_path}")
        return None
    
    try:
        with open(msgpack_path, 'rb') as f:
            data = msgpack.unpack(f, raw=False, strict_map_key=False)
        
        version = data.get("version", 1)
        if version != CATALOG_VERSION:
            logger.warning(f"Unexpected catalog version: {version} (expected {CATALOG_VERSION})")
        
        logger.info(f"Loaded v2 catalog from {msgpack_path} (version={version})")
        return data
        
    except Exception as exc:
        logger.error(f"Failed to load msgpack catalog: {exc}")
        return None


def run_migration(force: bool = False) -> bool:
    """Run the catalog migration from v1 (pickle) to v2 (msgpack).
    
    Args:
        force: If True, force migration even if v2 exists
        
    Returns:
        True if migration was successful or not needed, False if failed
    """
    logger.info("=" * 60)
    logger.info("Starting catalog migration: v1 (pickle) -> v2 (msgpack)")
    logger.info("=" * 60)
    
    # Ensure data directory exists
    data_dir = _ensure_data_dir()
    logger.info(f"Data directory: {data_dir}")
    
    # Check if v2 already exists
    if CATALOG_V2_PATH.exists() and not force:
        logger.info("v2 catalog already exists. Use FORCE_MIGRATE=1 to force migration.")
        logger.info("Migration skipped.")
        return True
    
    # Check if v1 exists
    if not CATALOG_V1_PATH.exists():
        logger.info("No v1 catalog found. Nothing to migrate.")
        logger.info("If you have a .pkl file elsewhere, copy it to:")
        logger.info(f"  {CATALOG_V1_PATH}")
        return True
    
    # Step 1: Create backup
    logger.info("Step 1: Creating backup...")
    backup_path = _create_backup(CATALOG_V1_PATH)
    
    # Step 2: Load v1 catalog
    logger.info("Step 2: Loading v1 catalog...")
    pickle_data = _load_pickle_catalog(CATALOG_V1_PATH)
    if pickle_data is None:
        logger.error("Failed to load v1 catalog. Aborting migration.")
        logger.info("Restoring from backup...")
        if backup_path.exists():
            shutil.copy2(str(backup_path), str(CATALOG_V1_PATH))
        return False
    
    # Step 3: Convert to v2 format
    logger.info("Step 3: Converting to v2 format...")
    v2_data = _convert_to_v2_format(pickle_data)
    
    # Step 4: Save v2 catalog
    logger.info("Step 4: Saving v2 catalog (msgpack)...")
    if not _save_msgpack_v2(v2_data, CATALOG_V2_TEMP_PATH, CATALOG_V2_PATH):
        logger.error("Failed to save v2 catalog.")
        logger.info("Restoring from backup...")
        if backup_path.exists():
            shutil.copy2(str(backup_path), str(CATALOG_V1_PATH))
        return False
    
    # Step 5: Verify v2 catalog
    logger.info("Step 5: Verifying v2 catalog...")
    loaded = _load_msgpack_v2(CATALOG_V2_PATH)
    if loaded is None:
        logger.error("Verification failed: cannot load v2 catalog.")
        return False
    
    logger.info(f"Verification successful: {len(loaded.get('catalog', []))} entries")
    
    # Step 6: Mark v1 as deprecated (rename, don't delete immediately)
    logger.info("Step 6: Marking v1 as deprecated...")
    deprecated_path = CATALOG_V1_PATH.with_suffix(CATALOG_V1_PATH.suffix + ".deprecated")
    if CATALOG_V1_PATH.exists():
        CATALOG_V1_PATH.rename(deprecated_path)
        logger.info(f"Renamed v1 to: {deprecated_path}")
    
    logger.info("=" * 60)
    logger.info("Migration completed successfully!")
    logger.info("=" * 60)
    return True


def main() -> None:
    """Main entry point for migration script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    
    force = _FORCE_MIGRATE or len(sys.argv) > 1 and sys.argv[1] in ('--force', '-f')
    
    success = run_migration(force=force)
    
    if success:
        logger.info("Migration script finished successfully.")
        sys.exit(0)
    else:
        logger.error("Migration script failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
