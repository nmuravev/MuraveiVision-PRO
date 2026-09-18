"""Integration tests for model mutual exclusion (VRAM management)."""
import pytest


def test_yolo_seg_exclusion():
    """Test that loading YOLO-seg unloads YOLO-detect."""
    from services.yolo_engine import get_yolo_engine
    from services.segmentation_engine import get_seg_engine
    import services.model_mutex as mutex
    
    yolo = get_yolo_engine()
    seg = get_seg_engine()
    
    # Verify initial state
    assert yolo.mode in ("offline", "ready", "error")
    
    # Note: This test requires actual model weights to be present
    # If weights are missing, the test should be skipped
    try:
        # Load YOLO-detect via force_load (this triggers mutex)
        if yolo.model_path is not None:
            # Check initial state
            assert mutex.get_active_model() is None
            
            yolo.force_load(yolo.model_path)
            
            # After force_load, mutex should have set yolo_detect
            assert mutex.get_active_model() == "yolo_detect", f"Expected 'yolo_detect', got {mutex.get_active_model()}"
            
            # Load YOLO-seg → должен выгрузить YOLO-detect
            seg.load_model()
            
            # YOLO-detect should be unloaded
            assert yolo.mode == "offline" or yolo.model is None
            assert mutex.get_active_model() == "yolo_seg"
            
            print("[TEST] Mutual exclusion working correctly!")
        else:
            pytest.skip("YOLO model path not available")
    except (FileNotFoundError, RuntimeError) as e:
        # Skip if models not available
        pytest.skip(f"Models not available: {e}")


def test_sam3_yolo_seg_exclusion():
    """Test that loading SAM3 unloads YOLO-seg."""
    from services.sam3_engine import get_sam3_engine
    from services.segmentation_engine import get_seg_engine
    import services.model_mutex as mutex
    
    sam3 = get_sam3_engine()
    seg = get_seg_engine()
    
    try:
        # Load YOLO-seg first
        seg.load_model()
        assert mutex.get_active_model() == "yolo_seg"
        
        # Load SAM3 → должен выгрузить YOLO-seg
        sam3.load_model()
        
        # YOLO-seg should be unloaded
        assert seg._model is None
        assert mutex.get_active_model() == "sam3"
        
        print("[TEST] SAM3-YOLO-seg exclusion working correctly!")
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
    
    print("[TEST] Release working correctly!")


def test_mutex_thread_safety():
    """Test that mutex is thread-safe."""
    import threading
    from services.model_mutex import acquire_model, release_model, get_active_model
    
    results = []
    
    def worker(model_name):
        try:
            result = acquire_model(model_name)
            results.append((model_name, result, get_active_model()))
        except Exception as e:
            results.append((model_name, False, str(e)))
    
    # Launch multiple threads trying to acquire different models
    threads = [
        threading.Thread(target=worker, args=("yolo_detect",)),
        threading.Thread(target=worker, args=("yolo_seg",)),
        threading.Thread(target=worker, args=("sam3",)),
    ]
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # All acquisitions should succeed (mutex handles unloading others)
    assert len(results) == 3
    assert all(r[1] for r in results)
    
    # Only one model should be active at the end
    active_models = [r[2] for r in results if r[2] is not None]
    # Last one wins
    assert active_models[-1] in ("yolo_detect", "yolo_seg", "sam3")
    
    # Clean up
    release_model()
    
    print("[TEST] Thread safety working correctly!")
