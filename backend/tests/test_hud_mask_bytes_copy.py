"""P1-8: HUD mask must not modify original JPEG bytes buffer."""
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.hud_exclusion import mask_jpeg_bytes, HudZones


class TestHUDMaskBytesCopy(unittest.TestCase):
    """Verify that mask_jpeg_bytes never mutates the caller's bytes buffer."""

    def test_mask_does_not_mutate_original_bytes(self):
        """Original bytes must remain identical after mask_jpeg_bytes call."""
        # Create a minimal valid JPEG (1x1 pixel)
        import cv2
        import numpy as np

        frame = np.full((100, 100, 3), 128, dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        original_jpeg = buf.tobytes()

        # Store snapshot of original bytes
        original_bytes = bytearray(original_jpeg)

        # Create zones that will trigger masking
        zones = HudZones(top=0.1, bottom=0.1, left=0.0, right=0.0, source="manual", ready=True)

        # Call mask_jpeg_bytes
        _result = mask_jpeg_bytes(original_jpeg, zones)

        # Verify original bytes were NOT modified
        self.assertEqual(bytearray(original_jpeg), original_bytes)

    def test_mask_with_no_zones_returns_original(self):
        """No zones → return original bytes unchanged."""
        import cv2
        import numpy as np

        frame = np.full((50, 50, 3), 64, dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        original_jpeg = buf.tobytes()

        result = mask_jpeg_bytes(original_jpeg, None)
        self.assertEqual(result, original_jpeg)

    def test_mask_with_empty_zones_returns_original(self):
        """Empty zones (no exclusion) → return original bytes unchanged."""
        import cv2
        import numpy as np

        frame = np.full((50, 50, 3), 64, dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        original_jpeg = buf.tobytes()

        zones = HudZones(ready=True, source="none")
        result = mask_jpeg_bytes(original_jpeg, zones)
        self.assertEqual(result, original_jpeg)

    def test_mask_with_empty_jpeg_returns_original(self):
        """Empty bytes → return empty bytes."""
        zones = HudZones(top=0.1, bottom=0.1, source="manual", ready=True)
        result = mask_jpeg_bytes(b"", zones)
        self.assertEqual(result, b"")

    def test_mask_result_is_valid_jpeg(self):
        """Masked result must be a valid JPEG that can be decoded."""
        import cv2
        import numpy as np

        frame = np.full((200, 200, 3), 200, dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        original_jpeg = buf.tobytes()

        zones = HudZones(top=0.15, bottom=0.15, left=0.1, right=0.1, source="manual", ready=True)
        result = mask_jpeg_bytes(original_jpeg, zones)

        # Result should be valid JPEG
        arr = np.frombuffer(result, dtype=np.uint8)
        decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.shape, (200, 200, 3))


if __name__ == "__main__":
    unittest.main()
