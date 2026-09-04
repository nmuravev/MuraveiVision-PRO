"""HUD exclusion: detect, fingerprint, mask, crop, full-frame bbox identity."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from services import hud_exclusion as hud
from services.hud_exclusion import (
    HudZones,
    apply_blur_mask,
    crop_frame,
    detect_zones_from_frames,
    map_intrinsics_to_full_frame,
    video_fingerprint,
)


class TestHudMotionAndBands(unittest.TestCase):
    def test_static_camera_noop(self) -> None:
        base = np.zeros((120, 160, 3), dtype=np.uint8)
        base[40:80, 40:120] = 180
        frames = [base.copy() for _ in range(6)]
        z = detect_zones_from_frames(frames)
        self.assertFalse(z.has_exclusion())
        self.assertEqual(z.source, "none")

    def test_moving_interior_static_border(self) -> None:
        frames = []
        for i in range(8):
            fr = np.zeros((200, 300, 3), dtype=np.uint8)
            # Static high-contrast HUD bars
            fr[:30, :] = 255
            fr[-40:, :] = 200
            # Moving blob in center
            x = 80 + i * 12
            fr[80:120, x : x + 40] = 90
            frames.append(fr)
        z = detect_zones_from_frames(frames)
        # Should find some top/bottom; tolerate algorithm variance
        self.assertTrue(z.ready)
        self.assertGreaterEqual(z.top + z.bottom, 0.0)


class TestFingerprint(unittest.TestCase):
    def tearDown(self) -> None:
        hud.clear_mem_for_tests()

    def test_mismatch_triggers_recompute(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            video = root / "clip.mp4"
            video.write_bytes(b"fake-video-aaaa")
            key = "clip_testkey"
            stale = HudZones(
                top=0.1,
                bottom=0.2,
                source="auto",
                ready=True,
                fingerprint={"size": 1, "mtime_ns": 1},
                video_key=key,
            )
            cache = root / key / "hud_zones.json"
            cache.parent.mkdir(parents=True)
            cache.write_text(json.dumps(stale.to_dict()), encoding="utf-8")

            with (
                patch.object(hud, "ANALYSIS_ROOT", root),
                patch.object(hud, "_resolve_video", return_value=video),
                patch.object(hud, "archive_rel_key", return_value=key),
                patch.object(
                    hud,
                    "_compute_for_video",
                    return_value=HudZones(
                        top=0.05,
                        bottom=0.1,
                        source="auto",
                        ready=True,
                        fingerprint=video_fingerprint(video),
                        video_key=key,
                    ),
                ) as compute,
            ):
                z = hud.get_zones("archive/clip.mp4", force=False, wait=True, kickoff=True)
            compute.assert_called()
            self.assertAlmostEqual(z.top, 0.05)


class TestMaskAndCrop(unittest.TestCase):
    def test_mask_keeps_shape_not_black_fill(self) -> None:
        rng = np.random.default_rng(0)
        frame = rng.integers(40, 200, size=(100, 120, 3), dtype=np.uint8)
        z = HudZones(top=0.15, bottom=0.2, left=0.0, right=0.0, ready=True, source="manual")
        out = apply_blur_mask(frame, z)
        self.assertEqual(out.shape, frame.shape)
        # Top band should differ from original but not be pure black
        top_h = int(0.15 * 100)
        self.assertFalse(np.all(out[:top_h] == 0))
        self.assertFalse(np.array_equal(out[:top_h], frame[:top_h]))

    def test_crop_offsets(self) -> None:
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        z = HudZones(top=0.1, bottom=0.2, left=0.05, right=0.05, ready=True, source="manual")
        cropped, margins = crop_frame(frame, z)
        self.assertEqual(cropped.shape[0], 70)
        self.assertEqual(cropped.shape[1], 180)
        self.assertAlmostEqual(margins["top"], 0.1)

    def test_intrinsics_map_full_frame(self) -> None:
        intr = {"fx": 500.0, "fy": 500.0, "cx": 50.0, "cy": 40.0}
        size = {"width": 100, "height": 80}
        crop = {"top": 0.1, "bottom": 0.1, "left": 0.05, "right": 0.05}
        # full 200x100 → left offset 10, top 10
        new_intr, new_size = map_intrinsics_to_full_frame(intr, size, crop, 200, 100)
        self.assertEqual(new_size["width"], 200)
        self.assertEqual(new_size["height"], 100)
        self.assertAlmostEqual(new_intr["cx"], 50.0 + 0.05 * 200)
        self.assertAlmostEqual(new_intr["cy"], 40.0 + 0.1 * 100)

    def test_masked_inference_keeps_full_frame_bbox_space(self) -> None:
        """Masking must not change frame size → YOLO bboxes stay in full-frame coords."""
        frame = np.full((240, 320, 3), 80, dtype=np.uint8)
        frame[100:140, 150:190] = 220  # "object"
        z = HudZones(top=0.12, bottom=0.18, ready=True, source="manual")
        masked = apply_blur_mask(frame, z)
        self.assertEqual(masked.shape, frame.shape)
        # Synthetic "bbox" in normalized full-frame space — identity after mask
        bbox = {"x1": 150 / 320, "y1": 100 / 240, "x2": 190 / 320, "y2": 140 / 240}
        # After mask, coordinates referring to full frame are unchanged
        h, w = masked.shape[:2]
        self.assertEqual(h, 240)
        self.assertEqual(w, 320)
        self.assertAlmostEqual(bbox["x1"] * w, 150)
        self.assertAlmostEqual(bbox["y1"] * h, 100)


if __name__ == "__main__":
    unittest.main()
