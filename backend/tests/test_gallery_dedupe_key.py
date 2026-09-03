"""Gallery near-duplicate grouping — keep in sync with src/lib/galleryDedupe.ts."""
from __future__ import annotations

import unittest


def gallery_dedupe_key(class_name: str, time_sec: float, bbox_x: float, bbox_y: float) -> str:
    t = round(time_sec)
    bx = round(bbox_x * 20)
    by = round(bbox_y * 20)
    return f"{class_name}|{t}|{bx}|{by}"


class GalleryDedupeKeyTests(unittest.TestCase):
    def test_same_second_and_class_collapse(self) -> None:
        a = gallery_dedupe_key("military_truck", 16.1, 0.10, 0.34)
        b = gallery_dedupe_key("military_truck", 16.4, 0.12, 0.34)
        self.assertEqual(a, b)

    def test_different_class_kept_apart(self) -> None:
        a = gallery_dedupe_key("military_truck", 16.0, 0.1, 0.1)
        b = gallery_dedupe_key("tank", 16.0, 0.1, 0.1)
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
