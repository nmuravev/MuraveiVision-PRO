"""Unit tests for unified event timeline (local detections + incoming network)."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services import db
from services import events as ev
from services import network as net


NOW = 1_700_000_000.0


class EventsTimelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._orig_path = db.DB_PATH
        self._orig_init = db._initialized
        self._orig_jwt = db._jwt_secret_cache
        db.DB_PATH = Path(self._tmp.name)
        db._initialized = False
        db._jwt_secret_cache = None
        db.init_db()

    def tearDown(self) -> None:
        db.DB_PATH = self._orig_path
        db._initialized = False
        db._jwt_secret_cache = self._orig_jwt
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass

    def _stamp(self, table: str, row_id: str, ts: float) -> None:
        conn = db._connect()
        try:
            conn.execute(f"UPDATE {table} SET created_at = ? WHERE id = ?", (float(ts), row_id))
            conn.commit()
        finally:
            conn.close()

    def _insert_det(self, *, class_name: str = "tank", time_sec: float = 12.5, **extra: object) -> dict:
        payload = {
            "time_sec": time_sec,
            "class_name": class_name,
            "bbox_x": 0.1,
            "bbox_y": 0.1,
            "bbox_w": 0.2,
            "bbox_h": 0.2,
            "source_video": "archive/clip.mp4",
            "confidence": 0.85,
        }
        payload.update(extra)
        return db.insert_detection(payload)

    def test_merges_local_and_incoming_network(self) -> None:
        local = self._insert_det(class_name="military_truck")
        incoming = net.add_target(
            direction="in",
            class_name="tank",
            confidence=0.7,
            source_base="Baza-1",
            notes="from hub",
            gps_lat=50.1,
            gps_lon=30.2,
        )
        net.add_target(direction="out", class_name="should_not_appear", source_base="self")
        self._stamp("detections", local["id"], NOW - 10)
        self._stamp("network_targets", incoming["id"], NOW - 5)
        with mock.patch("services.events.time.time", return_value=NOW):
            rows = ev.list_timeline(window=300, limit=100)
        types = {r["id"]: r["type"] for r in rows}
        self.assertEqual(types[local["id"]], "local_detection")
        self.assertEqual(types[incoming["id"]], "network_target")
        self.assertEqual(len(rows), 2)
        net_row = next(r for r in rows if r["id"] == incoming["id"])
        self.assertEqual(net_row["source_base"], "Baza-1")
        self.assertIsNone(net_row["time_sec"])
        loc_row = next(r for r in rows if r["id"] == local["id"])
        self.assertIsNone(loc_row["source_base"])
        self.assertEqual(loc_row["time_sec"], 12.5)
        self.assertEqual(loc_row["source_video"], "clip.mp4")

    def test_sorts_newest_created_at_first(self) -> None:
        older = self._insert_det(class_name="old")
        newer = net.add_target(direction="in", class_name="new", source_base="Baza-2")
        self._stamp("detections", older["id"], NOW - 40)
        self._stamp("network_targets", newer["id"], NOW - 1)
        with mock.patch("services.events.time.time", return_value=NOW):
            rows = ev.list_timeline(window=300, limit=100)
        self.assertEqual([r["id"] for r in rows], [newer["id"], older["id"]])

    def test_window_excludes_old_events(self) -> None:
        stale = self._insert_det(class_name="stale")
        fresh = self._insert_det(class_name="fresh")
        self._stamp("detections", stale["id"], NOW - 120)
        self._stamp("detections", fresh["id"], NOW - 5)
        with mock.patch("services.events.time.time", return_value=NOW):
            rows = ev.list_timeline(window=30, limit=100)
        ids = {r["id"] for r in rows}
        self.assertIn(fresh["id"], ids)
        self.assertNotIn(stale["id"], ids)

    def test_limit_clips_after_merge(self) -> None:
        ids: list[str] = []
        for i in range(5):
            row = self._insert_det(class_name=f"c{i}")
            self._stamp("detections", row["id"], NOW - (5 - i))
            ids.append(row["id"])
        with mock.patch("services.events.time.time", return_value=NOW):
            rows = ev.list_timeline(window=300, limit=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["id"] for r in rows], [ids[-1], ids[-2]])

    def test_skips_deleted_detections(self) -> None:
        gone = self._insert_det(class_name="gone", is_deleted=1)
        self._stamp("detections", gone["id"], NOW - 2)
        with mock.patch("services.events.time.time", return_value=NOW):
            rows = ev.list_timeline(window=300, limit=100)
        self.assertEqual(rows, [])

    def test_clamps_window_and_limit(self) -> None:
        self.assertEqual(ev._clamp_window(1), 10.0)
        self.assertEqual(ev._clamp_window(99_999), 86400.0)
        self.assertEqual(ev._clamp_limit(0), 1)
        self.assertEqual(ev._clamp_limit(999), 200)
