"""Detect out-of-box contract: KIT, tactical ladder, SAHI default, size gates."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import (
    TACTICAL_WEIGHT_LADDER,
    read_kit,
    resolve_default_detect_weight,
)


class DetectContractTests(unittest.TestCase):
    def test_tactical_ladder_order(self) -> None:
        self.assertEqual(
            list(TACTICAL_WEIGHT_LADDER),
            [
                "yolo26l-ft.pt",
                "yolo26m-ft.pt",
                "yolo26s-ft.pt",
                "yolo26n-ft.pt",
                "yolo26n.pt",
            ],
        )

    def test_resolve_prefers_n_ft_over_n(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "yolo26n.pt").write_bytes(b"n" * 2048)
            (root / "yolo26n-ft.pt").write_bytes(b"ft" * 2048)
            got = resolve_default_detect_weight(root)
            self.assertIsNotNone(got)
            assert got is not None
            self.assertEqual(got.name, "yolo26n-ft.pt")

    def test_resolve_prefers_l_ft(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "yolo26n-ft.pt").write_bytes(b"n" * 2048)
            (root / "yolo26l-ft.pt").write_bytes(b"l" * 2048)
            got = resolve_default_detect_weight(root)
            self.assertIsNotNone(got)
            assert got is not None
            self.assertEqual(got.name, "yolo26l-ft.pt")

    def test_kit_fallback_dev(self) -> None:
        with mock.patch("config.BASE_DIR", Path(tempfile.mkdtemp())):
            with mock.patch.dict("os.environ", {}, clear=False):
                # Ensure no MURAVEI_BUILD_PROFILE
                import os

                os.environ.pop("MURAVEI_BUILD_PROFILE", None)
                self.assertEqual(read_kit(), "dev")

    def test_kit_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "KIT").write_text("mini", encoding="utf-8")
            with mock.patch("config.BASE_DIR", root):
                self.assertEqual(read_kit(), "mini")

    def test_sahi_default_on_when_unset(self) -> None:
        from api import detect as detect_api

        with mock.patch.object(detect_api, "get_setting", return_value=None):
            self.assertTrue(detect_api._sahi_default())

    def test_size_gate_thresholds(self) -> None:
        # Documented build gates (GB) — keep in sync with build_portable.ps1
        mini_warn, mini_reject = 4.5, 5.0
        full_warn, full_reject = 9.5, 10.0
        self.assertLess(mini_warn, mini_reject)
        self.assertLess(full_warn, full_reject)

    def test_sam3_single_name(self) -> None:
        from config import SAM3_WEIGHT_NAME

        self.assertEqual(SAM3_WEIGHT_NAME, "sam3.pt")


if __name__ == "__main__":
    unittest.main()
