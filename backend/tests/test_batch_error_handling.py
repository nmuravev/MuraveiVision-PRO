"""Test batch error handling in yolo_engine._boxes_to_objects.

Verifies that P1-10: individual box errors don't break the entire batch.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))


class TestBatchErrorHandling(unittest.TestCase):
    """Test per-box error isolation in _boxes_to_objects."""

    def _make_mock_box(self, cls_id=0, conf=0.5, xyxy=(0.1, 0.1, 0.9, 0.9), box_id=None):
        """Create a mock box object with proper tensor-like attributes."""
        mock_box = MagicMock()
        
        # Mock cls
        mock_cls = MagicMock()
        mock_cls[0].item.return_value = cls_id
        mock_box.cls = mock_cls
        
        # Mock conf
        mock_conf = MagicMock()
        mock_conf[0].item.return_value = conf
        mock_box.conf = mock_conf
        
        # Mock xyxy
        mock_xyxy = MagicMock()
        mock_xyxy[0].tolist.return_value = list(xyxy)
        mock_box.xyxy = mock_xyxy
        
        # Mock id
        if box_id is not None:
            mock_id = MagicMock()
            mock_id[0].item.return_value = box_id
            mock_box.id = mock_id
        else:
            mock_box.id = None
        
        return mock_box

    def test_normal_batch_returns_all_objects(self):
        """Normal batch with valid boxes should return objects (at least 1)."""
        from services.yolo_engine import YoloEngine
        
        engine = YoloEngine.__new__(YoloEngine)
        engine._names = {0: "soldier", 1: "vehicle"}
        engine.kind = "yolo26-closed"
        
        mock_result = MagicMock()
        mock_result.boxes = [
            self._make_mock_box(cls_id=0, conf=0.8),
            self._make_mock_box(cls_id=1, conf=0.7),
        ]
        mock_result.names = {0: "soldier", 1: "vehicle"}
        
        objects = engine._boxes_to_objects(mock_result, orig_w=100, orig_h=100, floor=0.25)
        
        # Should have at least 1 object (some may be filtered by is_scene_class)
        self.assertGreaterEqual(len(objects), 1)

    def test_single_box_error_does_not_break_batch(self):
        """One bad box should be skipped, others should still be processed."""
        from services.yolo_engine import YoloEngine
        
        engine = YoloEngine.__new__(YoloEngine)
        engine._names = {0: "soldier", 1: "vehicle"}
        engine.kind = "yolo26-closed"
        
        # First box is normal, second box will raise exception
        good_box = self._make_mock_box(cls_id=0, conf=0.8)
        bad_box = MagicMock()
        bad_box.cls[0].item.side_effect = RuntimeError("tensor index out of range")
        
        mock_result = MagicMock()
        mock_result.boxes = [good_box, bad_box]
        mock_result.names = {0: "soldier", 1: "vehicle"}
        
        objects = engine._boxes_to_objects(mock_result, orig_w=100, orig_h=100, floor=0.25)
        
        # Should have 1 object (good box), bad box skipped
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0]["class_en"], "soldier")

    def test_all_boxes_error_returns_empty(self):
        """If all boxes fail, should return empty list (not crash)."""
        from services.yolo_engine import YoloEngine
        
        engine = YoloEngine.__new__(YoloEngine)
        engine._names = {0: "soldier"}
        engine.kind = "yolo26-closed"
        
        bad_box1 = MagicMock()
        bad_box1.cls[0].item.side_effect = RuntimeError("error 1")
        
        bad_box2 = MagicMock()
        bad_box2.cls[0].item.side_effect = RuntimeError("error 2")
        
        mock_result = MagicMock()
        mock_result.boxes = [bad_box1, bad_box2]
        mock_result.names = {0: "soldier"}
        
        objects = engine._boxes_to_objects(mock_result, orig_w=100, orig_h=100, floor=0.25)
        
        self.assertEqual(len(objects), 0)

    def test_bbox_calculation_error_skips_box(self):
        """Error in bbox calculation should skip that box only."""
        from services.yolo_engine import YoloEngine
        
        engine = YoloEngine.__new__(YoloEngine)
        engine._names = {0: "soldier"}
        engine.kind = "yolo26-closed"
        
        good_box = self._make_mock_box(cls_id=0, conf=0.8)
        
        bad_box = MagicMock()
        # Good cls/conf, but bad xyxy
        bad_box.cls = MagicMock()
        bad_box.cls[0].item.return_value = 1
        bad_box.conf = MagicMock()
        bad_box.conf[0].item.return_value = 0.7
        bad_box.xyxy[0].tolist.side_effect = ValueError("invalid xyxy")
        bad_box.id = None
        
        mock_result = MagicMock()
        mock_result.boxes = [good_box, bad_box]
        mock_result.names = {0: "soldier", 1: "vehicle"}
        
        objects = engine._boxes_to_objects(mock_result, orig_w=100, orig_h=100, floor=0.25)
        
        # Should have 1 object (good box)
        self.assertEqual(len(objects), 1)


if __name__ == "__main__":
    unittest.main()
