"""Regression: BASE_DIR must come from leaf config (no circular import via main)."""
from __future__ import annotations

import importlib
import unittest
from pathlib import Path


class ConfigBaseDirTests(unittest.TestCase):
    def test_base_dir_from_config(self) -> None:
        from config import BASE_DIR, DIST_DIR

        cfg = Path(__file__).resolve().parents[1] / "config.py"
        self.assertTrue(cfg.is_file())
        self.assertEqual(BASE_DIR.resolve(), cfg.resolve().parent.parent)
        self.assertEqual(DIST_DIR, BASE_DIR / "dist")

    def test_yolo_engine_imports_without_main_cycle(self) -> None:
        mod = importlib.import_module("services.yolo_engine")
        self.assertTrue(hasattr(mod, "get_yolo_engine"))
        src = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("from main import BASE_DIR", src)
        self.assertIn("from config import BASE_DIR", src)

    def test_detect_router_imports_clean(self) -> None:
        """api.detect → yolo_engine must load without initializing main routers."""
        detect = importlib.import_module("api.detect")
        self.assertTrue(hasattr(detect, "router"))


if __name__ == "__main__":
    unittest.main()
