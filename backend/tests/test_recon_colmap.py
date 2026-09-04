"""Unit tests for recon_colmap helpers (matcher, frame budget, honest errors)."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import recon_colmap as rc


class TestChooseMatcher(unittest.TestCase):
    def test_video_defaults_to_sequential(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COLMAP_MATCHER", None)
            self.assertEqual(rc.choose_matcher(121, source="video"), "sequential")
            self.assertEqual(rc.choose_matcher(40, source="video"), "sequential")

    def test_photos_small_may_exhaustive(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COLMAP_MATCHER", None)
            self.assertEqual(rc.choose_matcher(50, source="photos"), "exhaustive")
            self.assertEqual(rc.choose_matcher(200, source="photos"), "sequential")

    def test_exhaustive_opt_in_refuses_large(self) -> None:
        with patch.dict(os.environ, {"COLMAP_MATCHER": "exhaustive"}, clear=False):
            self.assertEqual(rc.choose_matcher(50, source="photos"), "exhaustive")
            # Large / video → still sequential to avoid O(n²) GPU blow-up
            self.assertEqual(rc.choose_matcher(200, source="video"), "sequential")


class TestMatcherCliArgs(unittest.TestCase):
    def test_sequential_includes_overlap(self) -> None:
        args = rc.matcher_cli_args("sequential", "db.db", overlap=12, use_gpu=True)
        self.assertEqual(args[0], "sequential_matcher")
        self.assertIn("--SequentialMatching.overlap", args)
        self.assertEqual(args[args.index("--SequentialMatching.overlap") + 1], "12")
        self.assertEqual(args[args.index("--SiftMatching.use_gpu") + 1], "1")

    def test_exhaustive_cpu_flag(self) -> None:
        args = rc.matcher_cli_args("exhaustive", "db.db", use_gpu=False)
        self.assertEqual(args[0], "exhaustive_matcher")
        self.assertEqual(args[args.index("--SiftMatching.use_gpu") + 1], "0")

    def test_feature_extractor_max_image_size(self) -> None:
        args = rc.feature_extractor_args("db.db", "frames", image_size=1600)
        self.assertEqual(args[0], "feature_extractor")
        self.assertEqual(args[args.index("--SiftExtraction.max_image_size") + 1], "1600")


class TestFrameBudget(unittest.TestCase):
    def test_clamp_high_fps(self) -> None:
        # 120 s @ 5 fps → 601 frames → clamp under 600
        fps = rc.clamp_fps_sample(0.0, 120.0, 5.0, max_n=600)
        self.assertLessEqual(int(120.0 * fps) + 1, 600)
        self.assertLess(fps, 5.0)

    def test_no_clamp_when_under_budget(self) -> None:
        self.assertAlmostEqual(rc.clamp_fps_sample(0.0, 120.0, 1.0, max_n=600), 1.0)


class TestFormatColmapError(unittest.TestCase):
    def test_ignores_info_dump(self) -> None:
        dump = (
            "I20260904 22:38:54.145318 20408 misc.cc:198] \n"
            "==============================================================================\n"
            "Exhaustive feature matching\n"
            "==============================================================================\n"
            "I20260904 22:38:54.219480 20408 feature_matching.cc:231] Matching block [1/3, 1/3]\n"
            "I20260904 22:39:02.251132 20408 feature_matching.cc:46]  in 8.032s\n"
        )
        msg = rc.format_colmap_error(15, dump, stage="exhaustive_matcher")
        self.assertIn("COLMAP exit 15", msg)
        self.assertNotIn("Matching block", msg)
        self.assertNotIn("I20260904", msg)
        self.assertIn("matcher", msg.lower())

    def test_prefers_error_lines(self) -> None:
        dump = (
            "I20260904 22:00:00.0 1 misc.cc:1] hello\n"
            "E20260904 22:00:01.0 1 sift.cc:99] Out of memory allocating GPU buffer\n"
        )
        msg = rc.format_colmap_error(1, dump, stage="feature_extractor")
        self.assertIn("Out of memory", msg)
        self.assertNotIn("I20260904", msg)


class TestRegistrationHint(unittest.TestCase):
    def test_ok_when_enough(self) -> None:
        self.assertIsNone(rc.registration_failure_message(100, 40))

    def test_ru_hint_when_few(self) -> None:
        msg = rc.registration_failure_message(100, 2)
        self.assertIsNotNone(msg)
        assert msg is not None
        self.assertIn("перекрытий", msg)

    def test_count_images_txt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "images.txt").write_text(
                "# Image list\n"
                "1 0.1 0 0 0 0 0 0 1 name.jpg\n"
                "\n"
                "2 0.1 0 0 0 0 0 0 1 name2.jpg\n"
                "1 2 3\n",
                encoding="utf-8",
            )
            self.assertEqual(rc.count_registered_images(d), 2)


if __name__ == "__main__":
    unittest.main()
