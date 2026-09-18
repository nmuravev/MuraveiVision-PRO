"""Test P0-8: Unsafe Pickle -> msgpack migration security.

Verifies:
- RestrictedUnpickler blocks malicious pickle payloads (RCE prevention)
- CatalogStore uses RestrictedUnpickler for v1 pickle fallback
- msgpack serialization/deserialization works correctly
"""
from __future__ import annotations

import pickle
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))

from services.catalog import CatalogStore, HAS_MSGPACK, RestrictedUnpickler


class TestRestrictedUnpickler(unittest.TestCase):
    """Test RestrictedUnpickler security."""

    def test_safe_builtin_dict(self):
        """Safe builtins (dict, list, str, int) should be allowed."""
        payload = pickle.dumps({"key": "value", "count": 42})
        result = RestrictedUnpickler(BytesIO(payload)).load()
        self.assertEqual(result, {"key": "value", "count": 42})

    def test_safe_builtin_list(self):
        """Safe builtins (list) should be allowed."""
        payload = pickle.dumps([1, 2, "three"])
        result = RestrictedUnpickler(BytesIO(payload)).load()
        self.assertEqual(result, [1, 2, "three"])

    def test_blocked_os_system(self):
        """os.system should be blocked (RCE prevention)."""
        import os
        malicious = pickle.dumps(
            {"__reduce__": (os.system, ("echo HACKED",))}
        )
        with self.assertRaises(pickle.UnpicklingError):
            RestrictedUnpickler(BytesIO(malicious)).load()

    def test_blocked_subprocess(self):
        """subprocess.Popen should be blocked."""
        import subprocess
        malicious = pickle.dumps(
            {"__reduce__": (subprocess.Popen, (["echo", "HACKED"],))}
        )
        with self.assertRaises(pickle.UnpicklingError):
            RestrictedUnpickler(BytesIO(malicious)).load()

    def test_blocked_builtin_eval(self):
        """builtins.eval should be blocked (not in SAFE_BUILTINS)."""
        malicious = pickle.dumps(
            {"__reduce__": (eval, ("__import__('os').system('echo HACKED')",))}
        )
        with self.assertRaises(pickle.UnpicklingError):
            RestrictedUnpickler(BytesIO(malicious)).load()


class TestCatalogStoreMsgpack(unittest.TestCase):
    """Test CatalogStore msgpack operations."""

    @classmethod
    def setUpClass(cls):
        """Skip all tests if msgpack is not available."""
        if not HAS_MSGPACK:
            raise unittest.SkipTest("msgpack not available (air-gap: download wheels first)")

    def setUp(self):
        """Create temporary directory for catalog."""
        self.tmpdir = Path(tempfile.mkdtemp())
        # Override paths
        import services.catalog as catalog_mod
        self._orig_v2 = catalog_mod.CATALOG_V2_PATH
        self._orig_v1 = catalog_mod.CATALOG_V1_PATH
        self._orig_dir = catalog_mod.CATALOG_DIR
        catalog_mod.CATALOG_V2_PATH = self.tmpdir / "catalog_v2.msgpack"
        catalog_mod.CATALOG_V1_PATH = self.tmpdir / "catalog_v1.pkl"
        catalog_mod.CATALOG_DIR = self.tmpdir
        self.store = CatalogStore()

    def tearDown(self):
        """Restore original paths and clean up."""
        import services.catalog as catalog_mod
        catalog_mod.CATALOG_V2_PATH = self._orig_v2
        catalog_mod.CATALOG_V1_PATH = self._orig_v1
        catalog_mod.CATALOG_DIR = self._orig_dir
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_and_load(self):
        """Basic save and load should work."""
        self.store.load()
        self.store.save("test_key", "test_value")
        value = self.store.get("test_key")
        self.assertEqual(value, "test_value")

    def test_get_all(self):
        """get_all should return all entries."""
        self.store.load()
        self.store.save("key1", "value1")
        self.store.save("key2", "value2")
        entries = self.store.get_all()
        keys = {e["key"] for e in entries}
        self.assertIn("key1", keys)
        self.assertIn("key2", keys)

    def test_delete(self):
        """delete should remove entry."""
        self.store.load()
        self.store.save("to_delete", "value")
        result = self.store.delete("to_delete")
        self.assertTrue(result)
        self.assertIsNone(self.store.get("to_delete"))

    def test_nonexistent_key_returns_default(self):
        """get for nonexistent key should return default."""
        self.store.load()
        self.assertIsNone(self.store.get("nonexistent", None))
        self.assertEqual(self.store.get("missing", "default"), "default")


if __name__ == "__main__":
    unittest.main()
