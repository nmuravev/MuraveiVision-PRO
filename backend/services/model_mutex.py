"""Model mutex: exclusive VRAM access for YOLO-detect, YOLO-seg, and SAM3.

Prevents multiple heavy models from loading simultaneously, which would
exceed GPU memory and cause OOM crashes.

Usage:
    from services.model_mutex import acquire_model
    
    acquire_model("yolo_detect")  # unloads other models first
    # ... use model ...
    acquire_model("yolo_seg")     # unloads yolo_detect first
"""
from __future__ import annotations

import threading
from typing import Literal

_model_lock = threading.Lock()
_active_model: str | None = None  # "yolo_detect" | "yolo_seg" | "sam3"


def acquire_model(model_name: str) -> bool:
    """
    Acquire exclusive access to a model type.
    Unloads all other models before returning.
    
    Args:
        model_name: One of "yolo_detect", "yolo_seg", "sam3"
        
    Returns:
        True if successfully acquired
    """
    global _active_model
    
    with _model_lock:
        # Already active — no-op
        if _active_model == model_name:
            return True
        
        # Unload current model
        if _active_model == "yolo_detect":
            try:
                from services.yolo_engine import get_yolo_engine
                get_yolo_engine().unload_model()
                print(f"[ModelMutex] Unloaded YOLO-detect")
            except Exception as e:
                print(f"[ModelMutex] Warning: failed to unload YOLO-detect: {e}")
        
        elif _active_model == "yolo_seg":
            try:
                from services.segmentation_engine import get_seg_engine
                get_seg_engine().unload_model()
                print(f"[ModelMutex] Unloaded YOLO-seg")
            except Exception as e:
                print(f"[ModelMutex] Warning: failed to unload YOLO-seg: {e}")
        
        elif _active_model == "sam3":
            try:
                from services.sam3_engine import get_sam3_engine
                get_sam3_engine().unload_model()
                print(f"[ModelMutex] Unloaded SAM3")
            except Exception as e:
                print(f"[ModelMutex] Warning: failed to unload SAM3: {e}")
        
        _active_model = model_name
        return True


def release_model(model_name: str | None = None) -> None:
    """Release currently active model."""
    global _active_model
    
    with _model_lock:
        if model_name and _active_model == model_name:
            _active_model = None
        elif not model_name:
            _active_model = None


def get_active_model() -> str | None:
    """Get currently active model type."""
    with _model_lock:
        return _active_model
