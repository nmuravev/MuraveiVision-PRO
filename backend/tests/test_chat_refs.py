"""Unit tests for chat detection:<id> token parsing."""
from __future__ import annotations

import unittest

from services.chat_refs import DETECTION_REF_RE, extract_detection_ids, format_detection_ref


class ChatRefsTests(unittest.TestCase):
    def test_extract_unique_order(self) -> None:
        body = "see detection:aabbccddee01 and again detection:aabbccddee01 then detection:112233445566"
        self.assertEqual(
            extract_detection_ids(body),
            ["aabbccddee01", "112233445566"],
        )

    def test_rejects_short_or_non_hex(self) -> None:
        self.assertEqual(extract_detection_ids("detection:abc detection:zzzzzzzzzzzz"), [])
        self.assertIsNone(DETECTION_REF_RE.search("detection:toolongbutnothex!!!!"))

    def test_format(self) -> None:
        self.assertEqual(format_detection_ref("AaBbCcDdEe01"), "detection:aabbccddee01")


if __name__ == "__main__":
    unittest.main()
