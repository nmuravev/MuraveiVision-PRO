"""Unit tests for field error catalog."""
from __future__ import annotations

import unittest

from services.error_catalog import (
    ERROR_CATALOG,
    build_error_payload,
    get_error_details,
)


class TestErrorCatalog(unittest.TestCase):
    def test_error_catalog_has_all_codes(self) -> None:
        for code in (400, 401, 403, 404, 409, 422, 429, 500, 503):
            self.assertIn(code, ERROR_CATALOG)
            self.assertTrue(ERROR_CATALOG[code])

    def test_get_error_details_returns_structure(self) -> None:
        result = get_error_details(404)
        self.assertIn("title_ru", result)
        self.assertIn("causes_ru", result)
        self.assertIn("solutions_ru", result)
        self.assertTrue(result["causes_ru"])
        self.assertTrue(result["solutions_ru"])
        self.assertEqual(result["name"], "NOT_FOUND")

    def test_get_error_details_matches_keywords(self) -> None:
        result = get_error_details(503, "model not loaded in VRAM")
        self.assertEqual(result["name"], "SERVICE_UNAVAILABLE")
        self.assertTrue(any("VRAM" in c or "модель" in c.lower() for c in result["causes_ru"]))

    def test_get_error_details_matches_da3_weights(self) -> None:
        result = get_error_details(503, "DA3_WEIGHTS_NOT_FOUND")
        self.assertEqual(result["name"], "DA3_WEIGHTS_NOT_FOUND")
        self.assertTrue(any("da3" in c.lower() for c in result["causes_ru"]))
        self.assertTrue(any("sidecars/da3/" in s for s in result["solutions_ru"]))

    def test_build_error_payload_keeps_detail(self) -> None:
        payload = build_error_payload(404, "File not found")
        self.assertEqual(payload["detail"], "File not found")
        err = payload["error"]
        self.assertEqual(err["code"], 404)
        self.assertEqual(err["name"], "NOT_FOUND")
        self.assertEqual(err["title"], "Ресурс не найден")
        self.assertIn("causes", err)
        self.assertIn("solutions", err)
        self.assertIn("#404", err["docs_url"])

    def test_unknown_code_fallback(self) -> None:
        result = get_error_details(418)
        self.assertEqual(result["name"], "UNKNOWN")
        self.assertTrue(result["title_ru"])


if __name__ == "__main__":
    unittest.main()
