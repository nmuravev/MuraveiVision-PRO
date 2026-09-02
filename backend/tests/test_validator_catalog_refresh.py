"""Unit tests for validator catalog auto-refresh on class override edits.

Covers Masterplan v3 task 1.3: after a class override PUT/DELETE, the
response validator's cached enabled-ID set must be invalidated so detections
with the newly enabled/disabled class_id are accepted/rejected without a
backend restart.
"""
from __future__ import annotations

import time
import unittest
from unittest import mock

from services.response_validator import ResponseValidator


def _det(class_id: int, confidence: float = 0.8) -> dict:
    return {
        "id": "trk-1",
        "class_id": class_id,
        "class_en": "x",
        "class_ru": "x",
        "confidence": confidence,
        "bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.3},
        "color": "#ef4444",
        "origin": "auto",
        "track_id": 1,
    }


class CatalogRefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ResponseValidator()
        # Start with a stale cache: class 42 NOT enabled.
        self.validator._enabled_ids = {5, 7}

    def _catalog_with_42(self):
        return [
            {"id": 5, "name_en": "tank", "enabled": True},
            {"id": 7, "name_en": "military_truck", "enabled": True},
            {"id": 42, "name_en": "new_vehicle", "enabled": True},
        ]

    def test_stale_cache_rejects_new_class(self) -> None:
        """Before refresh, a detection with the new class_id is rejected."""
        res = self.validator.validate_detection(_det(class_id=42))
        self.assertFalse(res.passed)
        self.assertTrue(
            any("not in enabled catalog" in r for r in res.reasons),
            res.reasons,
        )

    def test_refresh_catalog_picks_up_newly_enabled_class(self) -> None:
        """After refresh_catalog() (re-reading the catalog), class 42 is accepted."""
        with mock.patch(
            "services.response_validator.get_class_catalog",
            return_value=self._catalog_with_42(),
        ):
            self.validator.refresh_catalog()
            known = self.validator._known_ids()
        self.assertIn(42, known)
        res = self.validator.validate_detection(_det(class_id=42))
        self.assertTrue(res.passed, res.reasons)

    def test_refresh_then_disable_drops_class(self) -> None:
        """After refresh with class 42 disabled, detections of 42 are rejected."""
        catalog = [
            {"id": 5, "name_en": "tank", "enabled": True},
            {"id": 7, "name_en": "military_truck", "enabled": True},
            {"id": 42, "name_en": "new_vehicle", "enabled": False},
        ]
        with mock.patch(
            "services.response_validator.get_class_catalog",
            return_value=catalog,
        ):
            self.validator.refresh_catalog()
            known = self.validator._known_ids()
        self.assertNotIn(42, known)
        res = self.validator.validate_detection(_det(class_id=42))
        self.assertFalse(res.passed)

    def test_refresh_clears_cache_so_next_read_reloads(self) -> None:
        """refresh_catalog sets _enabled_ids to None, forcing reload on next access."""
        self.validator.refresh_catalog()
        self.assertIsNone(self.validator._enabled_ids)

    def test_classes_api_handler_calls_refresh_on_put(self) -> None:
        """Integration: the PUT /api/classes/overrides/{id} handler calls refresh_catalog."""
        import api.classes_api as ca

        captured: list[bool] = []

        class _FakeValidator:
            def refresh_catalog(self) -> None:
                captured.append(True)

        # Drive the handler logic directly: it calls upsert + invalidate + refresh.
        with mock.patch.object(ca, "upsert_class_override", return_value={"class_id": 42}), \
             mock.patch.object(ca, "invalidate_class_cache"), \
             mock.patch.object(ca, "get_class_catalog", return_value=[]), \
             mock.patch(
                 "services.response_validator.get_validator",
                 return_value=_FakeValidator(),
             ):
            # Body is a pydantic model; build it.
            body = ca.OverridePatch(enabled=True)
            import asyncio

            row = asyncio.run(
                ca.classes_override_put(42, body, _user={"role": "engineer"})
            )
        self.assertTrue(captured, "refresh_catalog was not called by PUT handler")
        self.assertTrue(row["ok"])

    def test_classes_api_handler_calls_refresh_on_delete(self) -> None:
        """Integration: the DELETE handler calls refresh_catalog."""
        import api.classes_api as ca

        captured: list[bool] = []

        class _FakeValidator:
            def refresh_catalog(self) -> None:
                captured.append(True)

        with mock.patch.object(ca, "delete_class_override", return_value=True), \
             mock.patch.object(ca, "invalidate_class_cache"), \
             mock.patch.object(ca, "get_class_catalog", return_value=[]), \
             mock.patch(
                 "services.response_validator.get_validator",
                 return_value=_FakeValidator(),
             ):
            import asyncio

            res = asyncio.run(
                ca.classes_override_delete(42, _user={"role": "engineer"})
            )
        self.assertTrue(captured, "refresh_catalog was not called by DELETE handler")
        self.assertTrue(res["ok"])


class CatalogTtlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ResponseValidator()

    def test_ttl_expiry_reloads_catalog(self) -> None:
        first = [{"id": 999, "name_en": "x", "enabled": True}]
        second = [{"id": 1, "name_en": "tank", "enabled": True}]
        with mock.patch(
            "services.response_validator.get_class_catalog",
            side_effect=[first, second],
        ):
            known = self.validator._known_ids()
            self.assertIn(999, known)
            self.validator._cache_timestamp = time.time() - 400
            known2 = self.validator._known_ids()
        self.assertNotIn(999, known2)
        self.assertIn(1, known2)
        self.assertGreater(self.validator._cache_timestamp, time.time() - 5)

    def test_within_ttl_keeps_stale_catalog(self) -> None:
        first = [{"id": 999, "name_en": "x", "enabled": True}]
        second = [{"id": 1, "name_en": "tank", "enabled": True}]
        with mock.patch(
            "services.response_validator.get_class_catalog",
            side_effect=[first, second],
        ) as patched:
            self.validator._known_ids()
            known = self.validator._known_ids()
        self.assertIn(999, known)
        self.assertEqual(patched.call_count, 1)

    def test_refresh_bypasses_ttl(self) -> None:
        first = [{"id": 999, "name_en": "x", "enabled": True}]
        second = [{"id": 1, "name_en": "tank", "enabled": True}]
        with mock.patch(
            "services.response_validator.get_class_catalog",
            side_effect=[first, second],
        ):
            self.assertIn(999, self.validator._known_ids())
            self.validator.refresh_catalog()
            known = self.validator._known_ids()
        self.assertNotIn(999, known)
        self.assertIn(1, known)

    def test_failure_keeps_old_cache(self) -> None:
        self.validator._enabled_ids = {5, 7}
        self.validator._cache_timestamp = time.time() - 400
        with mock.patch(
            "services.response_validator.get_class_catalog",
            side_effect=RuntimeError("boom"),
        ):
            known = self.validator._known_ids()
        self.assertEqual(known, {5, 7})
        self.assertGreater(self.validator._cache_timestamp, time.time() - 5)


if __name__ == "__main__":
    unittest.main()
