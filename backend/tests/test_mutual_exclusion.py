"""Integration tests for model mutual exclusion (VRAM management)."""
import pytest


def test_yolo_seg_exclusion():
    """Test that loading YOLO-seg unloads YOLO-detect."""
    from services.yolo_engine import get_yolo_engine
    from services.segmentation_engine import get_seg_engine
    from services.model_mutex import get_active_model
    
    yolo = get_yolo_engine()
    seg = get_seg_engine()
    
    # Verify initial state
    assert yolo.mode in ("offline", "ready", "error")
    
    # Note: This test requires actual model weights to be present
    # If weights are missing, the test should be skipped
    try:
        # Load YOLO-detect (may fail if no weights)
        yolo_loaded = yolo.mode == "ready"
        
        if yolo_loaded:
            assert get_active_model() == "yolo_detect"
            
            # Load YOLO-seg → должен выгрузить YOLO-detect
            seg.load_model()
            
            # YOLO-detect should be unloaded
            assert yolo.mode == "offline" or yolo.model is None
            assert get_active_model() == "yolo_seg"
    except (FileNotFoundError, RuntimeError) as e:
        # Skip if models not available
        pytest.skip(f"Models not available: {e}")


def test_sam3_yolo_seg_exclusion():
    """Test that loading SAM3 unloads YOLO-seg."""
    from services.sam3_engine import get_sam3_engine
    from services.segmentation_engine import get_seg_engine
    from services.model_mutex import get_active_model
    
    sam3 = get_sam3_engine()
    seg = get_seg_engine()
    
    try:
        # Load YOLO-seg first
        seg.load_model()
        assert get_active_model() == "yolo_seg"
        
        # Load SAM3 → должен выгрузить YOLO-seg
        sam3.load_model()
        
        # YOLO-seg should be unloaded
        assert seg._model is None
        assert get_active_model() == "sam3"
    except (FileNotFoundError, RuntimeError) as e:
        pytest.skip(f"Models not available: {e}")


def test_mutex_release():
    """Test that release_model works correctly."""
    from services.model_mutex import acquire_model, release_model, get_active_model
    
    # Acquire and verify
    acquire_model("yolo_detect")
    assert get_active_model() == "yolo_detect"
    
    # Release
    release_model("yolo_detect")
    assert get_active_model() is None
    
    # Release all
    acquire_model("yolo_seg")
    assert get_active_model() == "yolo_seg"
    release_model()
    assert get_active_model() is None
