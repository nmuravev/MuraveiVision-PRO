from __future__ import annotations

import unittest

from services.autolabel import parse_autolabel_result


class Sprint4Tests(unittest.TestCase):
    def test_autolabel_json_is_clamped_and_catalog_scoped(self) -> None:
        catalog = [{"id": 7, "name_en": "military_truck", "name_ru": "Военный грузовик"}]
        proposal = parse_autolabel_result(
            '```json\n{"class_id": 7, "confidence": 1.4, "reason": "shape"}\n```',
            catalog,
        )
        self.assertEqual(proposal["class_name"], "military_truck")
        self.assertEqual(proposal["confidence"], 1.0)
        with self.assertRaises(ValueError):
            parse_autolabel_result('{"class_id": 99, "confidence": 0.8}', catalog)

if __name__ == "__main__":
    unittest.main()
