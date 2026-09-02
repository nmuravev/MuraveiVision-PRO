"""Find-similar: cosine ranking, SQLite embedding cache, hist fallback."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from services import db
from services import similarity as sim


class SimilarityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._orig_path = db.DB_PATH
        self._orig_init = db._initialized
        db.DB_PATH = Path(self._tmp.name)
        db._initialized = False
        db.init_db()
        self._crops = Path(tempfile.mkdtemp())
        self._hook_calls = 0
        self._prev_hook = sim._embed_hook
        self._prev_force = sim._force_method
        sim._force_method = sim.METHOD_HIST
        sim._embed_hook = self._hook

    def tearDown(self) -> None:
        sim._embed_hook = self._prev_hook
        sim._force_method = self._prev_force
        db.DB_PATH = self._orig_path
        db._initialized = False
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass
        for p in self._crops.glob("*"):
            try:
                p.unlink()
            except OSError:
                pass
        try:
            self._crops.rmdir()
        except OSError:
            pass

    def _hook(self, path: Path, method: str) -> np.ndarray:
        self._hook_calls += 1
        name = path.stem
        if name == "a":
            vec = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        elif name == "b":
            vec = np.array([0.95, 0.05, 0.0, 0.0], dtype=np.float32)
        else:
            vec = np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32)
        return vec / (np.linalg.norm(vec) or 1.0)

    def _jpeg(self, stem: str) -> Path:
        path = self._crops / f"{stem}.jpg"
        Image.new("RGB", (48, 48), (40, 80, 120)).save(path, "JPEG")
        return path

    def _insert(self, stem: str, class_name: str = "tank", source: str = "archive/a.mp4") -> dict:
        crop = self._jpeg(stem)
        return db.insert_detection(
            {
                "source_video": source,
                "time_sec": 1.0,
                "class_name": class_name,
                "bbox_x": 0.1,
                "bbox_y": 0.1,
                "bbox_w": 0.2,
                "bbox_h": 0.2,
                "crop_path": str(crop),
                "origin": "manual",
            }
        )

    def test_cosine_ranks_closer_first(self) -> None:
        a = np.array([1.0, 0.0], dtype=np.float32)
        close = np.array([0.9, 0.1], dtype=np.float32)
        far = np.array([0.0, 1.0], dtype=np.float32)
        self.assertGreater(sim.cosine(a, close), sim.cosine(a, far))

    def test_cache_skips_second_embed(self) -> None:
        row = self._insert("a")
        first = sim.embed_for_row(row, method=sim.METHOD_HIST)
        self.assertIsNotNone(first)
        n = self._hook_calls
        second = sim.embed_for_row(row, method=sim.METHOD_HIST)
        self.assertIsNotNone(second)
        self.assertEqual(self._hook_calls, n)
        assert first is not None and second is not None
        np.testing.assert_allclose(first[0], second[0])

    def test_mtime_change_recomputes(self) -> None:
        row = self._insert("a")
        sim.embed_for_row(row, method=sim.METHOD_HIST)
        n = self._hook_calls
        crop = Path(str(row["crop_path"]))
        os.utime(crop, (crop.stat().st_atime, crop.stat().st_mtime + 5))
        sim.embed_for_row(row, method=sim.METHOD_HIST)
        self.assertEqual(self._hook_calls, n + 1)

    def test_no_crop_raises(self) -> None:
        row = db.insert_detection(
            {
                "source_video": "archive/none.mp4",
                "time_sec": 0,
                "class_name": "tank",
                "bbox_x": 0.1,
                "bbox_y": 0.1,
                "bbox_w": 0.2,
                "bbox_h": 0.2,
                "origin": "manual",
            }
        )
        with self.assertRaises(ValueError) as ctx:
            sim.find_similar(row["id"])
        self.assertIn("crop", str(ctx.exception).lower())

    def test_hist_path_without_clip(self) -> None:
        probe = self._insert("a")
        close = self._insert("b")
        _far = self._insert("c")
        with mock.patch.object(sim, "clip_available", return_value=False):
            sim._force_method = None
            out = sim.find_similar(probe["id"], top_k=5, same_class=True)
        self.assertEqual(out["method"], sim.METHOD_HIST)
        self.assertEqual(out["query_id"], probe["id"])
        ids = [r["id"] for r in out["results"]]
        self.assertEqual(ids[0], close["id"])
        self.assertIn(_far["id"], ids)


if __name__ == "__main__":
    unittest.main()
