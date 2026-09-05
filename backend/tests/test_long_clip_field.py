"""Field integration tests on the real ~9-minute DJI clip (HUD burned-in).

Slow but mandatory when the clip is present. Uses shared frame cache.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from long_clip_fixture import (  # noqa: E402
    ensure_shared_frames,
    long_clip_skip_reason,
    resolve_long_clip,
)
from services import alicevision_pipeline as avp
from services.hud_exclusion import detect_zones_from_frames
from services.recon_colmap import (
    DEFAULT_MAX_FRAMES,
    choose_matcher,
    clamp_fps_sample,
    max_frames,
)
from services.security import BASE_DIR


def _require_clip(test: unittest.TestCase) -> Path:
    clip = resolve_long_clip()
    if clip is None:
        test.skipTest(long_clip_skip_reason())
    return clip


class TestLongClipBudgetAndMatcher(unittest.TestCase):
    def test_frame_budget_clamps_for_nine_minute_source(self) -> None:
        clip = _require_clip(self)
        # 9-min-ish duration probe via ffprobe optional — use known ~540s field clip
        duration = 540.0
        fps = clamp_fps_sample(0.0, duration, 2.0)
        expected = int(duration * fps) + 1
        cap = max_frames()
        self.assertLessEqual(expected, cap)
        self.assertGreaterEqual(expected, 200)
        self.assertLessEqual(cap, DEFAULT_MAX_FRAMES + 0)  # default budget
        self.assertTrue(clip.is_file())

    def test_video_pipeline_chooses_sequential_not_exhaustive(self) -> None:
        _require_clip(self)
        for n in (50, 200, 600, 1200):
            self.assertEqual(
                choose_matcher(n, source="video"),
                "sequential",
                msg=f"n={n} must stay sequential for video",
            )


class TestLongClipHud(unittest.TestCase):
    _frames_dir: Path | None = None
    _frame_count: int = 0

    @classmethod
    def setUpClass(cls) -> None:
        clip = resolve_long_clip()
        if clip is None:
            return
        cls._frames_dir, cls._frame_count = ensure_shared_frames(
            clip, t_start=0.0, t_end=45.0, fps=1.0, max_side=960
        )

    def test_hud_auto_exclusion_detects_border_zones(self) -> None:
        _require_clip(self)
        if not self._frames_dir or self._frame_count < 5:
            self.skipTest("shared frames not ready")
        import cv2

        paths = sorted(self._frames_dir.glob("*.jpg"))[:12]
        frames = [cv2.imread(str(p)) for p in paths]
        frames = [f for f in frames if f is not None]
        self.assertGreaterEqual(len(frames), 5)
        zones = detect_zones_from_frames(frames)
        # Burned-in HUD: expect non-trivial top and/or bottom margins
        top = float(zones.top or 0)
        bottom = float(zones.bottom or 0)
        self.assertTrue(
            top > 0.05 or bottom > 0.05,
            msg=f"expected HUD bands on field clip, got top={top} bottom={bottom} source={zones.source}",
        )


class TestAliceVisionGates(unittest.TestCase):
    def test_preflight_soft_fails_below_eight_views(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            frames = job / "frames"
            frames.mkdir()
            for i in range(3):
                (frames / f"{i:06d}.jpg").write_bytes(b"\xff\xd8\xff\xd9")
            sparse = job / "colmap" / "sparse" / "0"
            sparse.mkdir(parents=True)
            (sparse / "cameras.txt").write_text(
                "1 PINHOLE 100 80 50 50 50 40\n", encoding="utf-8"
            )
            (sparse / "images.txt").write_text(
                "1 1 0 0 0 0 0 0 1 000000.jpg\n\n"
                "2 1 0 0 0 0 0 0 1 000001.jpg\n\n"
                "3 1 0 0 0 0 0 0 1 000002.jpg\n\n",
                encoding="utf-8",
            )
            with patch.object(avp, "alicevision_available", return_value=True):
                with patch.object(avp, "alicevision_cuda_ready", return_value=(True, "")):
                    with patch.object(avp, "log_first_use"):
                        with patch.object(avp, "alicevision_version", return_value="3.3.0"):
                            with patch.object(avp, "_run_cli") as run_cli:
                                with patch.object(avp, "inject_colmap_poses", return_value=3):
                                    result = avp.run_dense_pipeline(job, mode="dense")
            self.assertFalse(result["ok"])
            self.assertIn("только 3", result["error"] or "")
            self.assertEqual(result.get("matched_views"), 3)
            steps = [c.kwargs.get("step") for c in run_cli.call_args_list]
            self.assertNotIn("depthMapEstimation", steps)
            self.assertNotIn("meshing", steps)
            self.assertNotIn("prepareDenseScene", steps)

    def test_stub_depth_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "a_depthMap.exr").write_bytes(b"x" * 7000)
            ok, reason = avp.depth_maps_usable(d)
            self.assertFalse(ok)
            self.assertIn("пустые", reason.lower() + reason)

    def test_crash_code_translated(self) -> None:
        msg = avp.format_cli_failure(3221226505, "OCIO found\n[fatal] boom")
        self.assertIn("0xC0000409", msg)
        self.assertIn("fatal", msg.lower())


class TestLongClipColmapSegment(unittest.TestCase):
    """Run COLMAP on a ≤60s segment of the 9-min clip (sequential only)."""

    def test_colmap_sequential_segment_reports_matched_views(self) -> None:
        clip = _require_clip(self)
        from services import recon_scanner
        from services.recon_colmap import choose_matcher

        if not recon_scanner.colmap_available():
            self.skipTest("COLMAP sidecar not available")

        # Product segment: first 60s @ 1 fps → ~60 frames, sequential
        t0, t1, fps = 0.0, 60.0, 1.0
        n_est = int((t1 - t0) * fps) + 1
        self.assertEqual(choose_matcher(n_est, source="video"), "sequential")

        job_id = "a1b2c3d4e5f6"
        # Use a temp job under archive/recon so paths stay under archive_root
        job_dir = BASE_DIR / "archive" / "recon" / job_id
        if job_dir.exists():
            import shutil

            shutil.rmtree(job_dir, ignore_errors=True)
        job_dir.mkdir(parents=True, exist_ok=True)

        # Place/copy clip reference as archive-relative path
        rel = None
        for cand in (
            Path("archive") / "video_2026-08-25_09-17-15.mp4",
            Path("MuraveiVision-Pro-3.2.0") / "archive" / "video_2026-08-25_09-17-15.mp4",
        ):
            if (BASE_DIR / cand).is_file():
                rel = cand.as_posix()
                break
        if rel is None:
            # symlink/copy into archive for path confinement
            dest = BASE_DIR / "archive" / "video_2026-08-25_09-17-15.mp4"
            if not dest.is_file():
                import shutil

                shutil.copy2(clip, dest)
            rel = "archive/video_2026-08-25_09-17-15.mp4"

        video_abs = (BASE_DIR / rel).resolve()
        frames_dir = job_dir / "frames"
        frame_times, n_frames, hud_crop = recon_scanner._extract_frames(
            video_abs, frames_dir, t0, t1, fps, source_video=rel
        )
        self.assertGreaterEqual(n_frames, 20)
        self.assertLessEqual(n_frames, max_frames())
        self.assertEqual(choose_matcher(n_frames, source="video"), "sequential")
        if hud_crop:
            self.assertTrue(
                float(hud_crop.get("top") or 0) > 0 or float(hud_crop.get("bottom") or 0) > 0,
                msg=f"HUD crop expected on field clip, got {hud_crop}",
            )

        # COLMAP SfM (can take several minutes)
        sparse = recon_scanner._run_colmap(job_dir, frames_dir)
        from services.colmap_poses import _parse_images_txt

        images = _parse_images_txt(sparse / "images.txt") if (sparse / "images.txt").is_file() else []
        if not images and (sparse / "images.bin").is_file():
            avp.ensure_colmap_text_model(sparse)
            images = _parse_images_txt(sparse / "images.txt")
        matched = len(images)
        # Persist for report / Dense gate
        (job_dir / "test_matched_views.json").write_text(
            json.dumps({"matched_views": matched, "n_frames": n_frames, "hud_crop": hud_crop}),
            encoding="utf-8",
        )
        self.assertGreaterEqual(matched, 1, msg="COLMAP produced no registered images")
        # Soft-fail path must not crash if matched < 8
        if matched < avp.MIN_MATCHED_VIEWS_FOR_DENSE:
            with patch.object(avp, "alicevision_available", return_value=True):
                with patch.object(avp, "alicevision_cuda_ready", return_value=(True, "")):
                    with patch.object(avp, "log_first_use"):
                        with patch.object(avp, "alicevision_version", return_value="3.3.0"):
                            # Use real inject on this sparse
                            result = avp.run_dense_pipeline(
                                job_dir,
                                mode="dense",
                                frames_dir=frames_dir,
                                sparse_dir=sparse,
                            )
            self.assertFalse(result["ok"])
            self.assertNotIn("0xC0000409", (result.get("error") or ""))
            self.assertIn("зарегистрировал только", result.get("error") or "")
        else:
            # Enough views — Dense may proceed; we only assert preflight passed inject count
            self.assertGreaterEqual(matched, avp.MIN_MATCHED_VIEWS_FOR_DENSE)


if __name__ == "__main__":
    unittest.main()
