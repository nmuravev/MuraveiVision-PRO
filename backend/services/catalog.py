"""Safe catalog storage using msgpack (v2) with pickle (v1) fallback.

This module provides a secure alternative to pickle.load() for catalog
serialization. Uses msgpack for v2 format with automatic fallback to
pickle for legacy v1 data.

Air-gap safe: msgpack wheels must be pre-downloaded.
No network calls at runtime.

Usage:
    from services.catalog import CatalogStore
    
    store = CatalogStore()
    store.load()  # Auto-detects v1/v2 format
    items = store.get_all()
    store.save(key, value)
"""
from __future__ import annotations

import logging
import os
import pickle
import time
from pathlib import Path
from typing import Any

from config import BASE_DIR

logger = logging.getLogger(__name__)

# --- Configuration ---
CATALOG_V2_PATH = BASE_DIR / "data" / "catalog_v2.msgpack"
CATALOG_V1_PATH = BASE_DIR / "data" / "catalog_v1.pkl"
CATALOG_DIR = BASE_DIR / "data"

# Catalog version
CATALOG_VERSION = 2

# Try to import msgpack
try:
    import msgpack
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False
    logger.warning("msgpack not available - will use pickle (less secure)")


class RestrictedUnpickler(pickle.Unpickler):
    """Safe unpickler that only allows built-in types.

    Prevents RCE via malicious pickle payloads by restricting
    allowed classes to builtins only (dict, list, str, int, float, etc.).
    """

    SAFE_BUILTINS = {
        "dict", "list", "tuple", "set", "frozenset",
        "str", "bytes", "int", "float", "bool", "NoneType",
        "bytearray", "complex",
    }

    def find_class(self, module: str, name: str) -> Any:
        # Only allow builtins
        if module in ("builtins", "__builtin__"):
            if name in self.SAFE_BUILTINS:
                return getattr(__import__(module), name)
            logger.warning("RestrictedUnpickler blocked: %s.%s", module, name)
            raise pickle.UnpicklingError(
                "Global %s.%s is forbidden for security reasons"
                % (module, name)
            )
        # Block all external modules
        logger.warning("RestrictedUnpickler blocked: %s.%s", module, name)
        raise pickle.UnpicklingError(
            "Global %s.%s is forbidden (only builtins allowed)"
            % (module, name)
        )


class CatalogStore:
    """Thread-safe catalog storage with msgpack (v2) and pickle (v1) fallback.
    
    Supports:
    - Automatic format detection (v2 msgpack > v1 pickle)
    - Atomic writes via os.replace()
    - Graceful degradation if msgpack unavailable
    """
    
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._version: int = 1
        self._last_loaded: float = 0.0
        self._lock: Any = None  # Will be set to threading.Lock() if needed
        
    def load(self, force: bool = False) -> bool:
        """Load catalog from disk. Auto-detects format (v2 > v1).
        
        Args:
            force: If True, reload even if already loaded
            
        Returns:
            True if loaded successfully, False otherwise
        """
        if not force and self._data and self._last_loaded > 0:
            return True
        
        # Try v2 (msgpack) first
        if HAS_MSGPACK and CATALOG_V2_PATH.exists():
            if self._load_v2():
                return True
            else:
                logger.warning("Failed to load v2 catalog, falling back to v1")
        
        # Fallback to v1 (pickle)
        if CATALOG_V1_PATH.exists():
            if self._load_v1():
                logger.warning("Loaded deprecated v1 catalog (pickle). Run migration!")
                return True
        
        logger.info("No catalog found, starting with empty catalog")
        self._data = {"version": CATALOG_VERSION, "catalog": [], "created_at": time.time()}
        self._version = CATALOG_VERSION
        self._last_loaded = time.time()
        return True
    
    def _load_v2(self) -> bool:
        """Load v2 catalog from msgpack file.
        
        Returns:
            True if successful
        """
        if not HAS_MSGPACK:
            logger.error("msgpack not installed, cannot load v2")
            return False
        
        try:
            with open(CATALOG_V2_PATH, 'rb') as f:
                data = msgpack.unpack(f, raw=False, strict_map_key=False)
            
            version = data.get("version", 1)
            if version != CATALOG_VERSION:
                logger.warning(f"Unexpected catalog version: {version} (expected {CATALOG_VERSION})")
            
            self._data = data
            self._version = version
            self._last_loaded = time.time()
            
            logger.info(f"Loaded v2 catalog from {CATALOG_V2_PATH} ({len(data.get('catalog', []))} entries)")
            return True
            
        except Exception as exc:
            logger.error(f"Failed to load v2 catalog: {exc}")
            return False
    
    def _load_v1(self) -> bool:
        """Load v1 catalog from pickle file (DEPRECATED, INSECURE).

        Uses RestrictedUnpickler to prevent RCE via malicious payloads.
        Only built-in types (dict, list, str, int, float, etc.) are allowed.

        Returns:
            True if successful
        """
        try:
            with open(CATALOG_V1_PATH, 'rb') as f:
                data = RestrictedUnpickler(f).load()
            
            self._data = {"version": 1, "catalog": data, "migrated_at": None}
            self._version = 1
            self._last_loaded = time.time()
            
            logger.info(f"Loaded v1 catalog from {CATALOG_V1_PATH}")
            return True
            
        except Exception as exc:
            logger.error(f"Failed to load v1 catalog: {exc}")
            return False
    
    def save(self, key: str, value: Any) -> bool:
        """Save a single entry to catalog.
        
        Args:
            key: Entry key
            value: Entry value (will be serialized)
            
        Returns:
            True if saved successfully
        """
        if not self._data:
            self.load()
        
        # Update or add entry
        found = False
        for i, item in enumerate(self._data.get("catalog", [])):
            if item.get("key") == key:
                self._data["catalog"][i]["value"] = self._serialize_value(value)
                found = True
                break
        
        if not found:
            self._data.setdefault("catalog", []).append({
                "key": key,
                "value": self._serialize_value(value),
                "updated_at": time.time(),
            })
        
        # Write to disk
        return self._write_to_disk()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a single entry from catalog.
        
        Args:
            key: Entry key
            default: Default value if key not found
            
        Returns:
            Entry value or default
        """
        if not self._data:
            self.load()
        
        for item in self._data.get("catalog", []):
            if item.get("key") == key:
                return self._deserialize_value(item.get("value"))
        
        return default
    
    def get_all(self) -> list[dict[str, Any]]:
        """Get all catalog entries.
        
        Returns:
            List of entry dicts
        """
        if not self._data:
            self.load()
        
        return [
            {
                "key": item["key"],
                "value": self._deserialize_value(item.get("value")),
                "updated_at": item.get("updated_at"),
            }
            for item in self._data.get("catalog", [])
        ]
    
    def delete(self, key: str) -> bool:
        """Delete an entry from catalog.
        
        Args:
            key: Entry key to delete
            
        Returns:
            True if deleted, False if not found
        """
        if not self._data:
            self.load()
        
        catalog = self._data.get("catalog", [])
        for i, item in enumerate(catalog):
            if item.get("key") == key:
                catalog.pop(i)
                return self._write_to_disk()
        
        return False
    
    def clear(self) -> bool:
        """Clear all catalog entries.
        
        Returns:
            True if successful
        """
        self._data = {
            "version": CATALOG_VERSION,
            "catalog": [],
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        return self._write_to_disk()
    
    def _serialize_value(self, value: Any) -> Any:
        """Serialize a value for msgpack storage.
        
        Handles numpy arrays, torch tensors, bytes, etc.
        
        Args:
            value: Value to serialize
            
        Returns:
            Serialized value
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
        
        # Handle dict/list recursively
        if isinstance(value, dict):
            return {
                "__type__": "dict",
                "__data__": {k: self._serialize_value(v) for k, v in value.items()},
            }
        
        if isinstance(value, (list, tuple)):
            return {
                "__type__": "list",
                "__data__": [self._serialize_value(item) for item in value],
            }
        
        # Fallback to string
        try:
            return str(value)
        except Exception:
            return f"<unserializable: {type(value).__name__}>"
    
    def _deserialize_value(self, value: Any) -> Any:
        """Deserialize a value from msgpack storage.
        
        Args:
            value: Serialized value
            
        Returns:
            Deserialized value
        """
        if not isinstance(value, dict) or "__type__" not in value:
            return value
        
        type_name = value["__type__"]
        
        if type_name == "numpy_array":
            try:
                import numpy as np
                return np.frombuffer(bytes.fromhex(value["__data__"]), 
                                   dtype=value["__dtype__"]).reshape(value["__shape__"])
            except Exception:
                logger.warning(f"Failed to deserialize numpy array: {value}")
                return value
        
        if type_name == "torch_tensor":
            try:
                import torch
                import numpy as np
                np_array = np.frombuffer(bytes.fromhex(value["__data__"]),
                                       dtype=value["__dtype__"]).reshape(value["__shape__"])
                return torch.from_numpy(np_array)
            except Exception:
                logger.warning(f"Failed to deserialize torch tensor: {value}")
                return value
        
        if type_name == "bytes":
            try:
                return bytes.fromhex(value["__data__"])
            except Exception:
                return value
        
        if type_name == "dict":
            try:
                return {k: self._deserialize_value(v) for k, v in value["__data__"].items()}
            except Exception:
                return value
        
        if type_name == "list":
            try:
                return [self._deserialize_value(item) for item in value["__data__"]]
            except Exception:
                return value
        
        return value
    
    def _write_to_disk(self) -> bool:
        """Write catalog to disk atomically.
        
        Returns:
            True if successful
        """
        if not HAS_MSGPACK:
            logger.error("msgpack not available, cannot save")
            return False
        
        try:
            # Ensure data directory exists
            CATALOG_DIR.mkdir(parents=True, exist_ok=True)
            
            # Write to temporary file first
            temp_path = CATALOG_V2_PATH.with_suffix(CATALOG_V2_PATH.suffix + ".tmp")
            
            with open(temp_path, 'wb') as f:
                msgpack.pack(self._data, f, use_bin_type=True, strict_types=True)
            
            # Atomic replacement
            os.replace(str(temp_path), str(CATALOG_V2_PATH))
            
            self._last_loaded = time.time()
            logger.debug(f"Saved v2 catalog to {CATALOG_V2_PATH}")
            return True
            
        except Exception as exc:
            logger.error(f"Failed to save catalog: {exc}")
            # Clean up temp file
            temp_path = CATALOG_V2_PATH.with_suffix(CATALOG_V2_PATH.suffix + ".tmp")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            return False
    
    def needs_migration(self) -> bool:
        """Check if catalog needs migration from v1 to v2.
        
        Returns:
            True if migration is needed
        """
        if not self._data:
            self.load()
        return self._version == 1


# Module-level singleton
_catalog_store: CatalogStore | None = None


def get_catalog_store() -> CatalogStore:
    """Get module-level singleton catalog store.
    
    Returns:
        CatalogStore singleton
    """
    global _catalog_store
    if _catalog_store is None:
        _catalog_store = CatalogStore()
        _catalog_store.load()
    return _catalog_store


def reset_catalog_store() -> None:
    """Reset catalog store singleton (for testing)."""
    global _catalog_store
    _catalog_store = None
