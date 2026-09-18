"""Integration tests for batch segmentation checkpoint and resume."""
import pytest
import json
import time


def test_checkpoint_save_load():
    """Test that checkpoint save and load work correctly."""
    from services.db import save_batch_seg_checkpoint, load_batch_seg_checkpoint
    
    task_id = "test-checkpoint-task"
    
    # Clean up any existing checkpoint
    import sqlite3
    from services.db import _connect, init_db
    init_db()
    conn = _connect()
    conn.execute("DELETE FROM batch_seg_jobs WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    
    # Save checkpoint
    checkpoint_data = {
        "video_path": "/test/video.mp4",
        "frame_step": 30,
        "confidence": 0.25,
        "status": "running",
        "last_frame_idx": 150,
        "total_frames": 1000,
        "results": [{"frame": 150, "objects": []}]
    }
    
    save_batch_seg_checkpoint(task_id, checkpoint_data)
    
    # Load and verify
    loaded = load_batch_seg_checkpoint(task_id)
    
    assert loaded is not None
    assert loaded["task_id"] == task_id
    assert loaded["last_frame_idx"] == 150
    assert loaded["status"] == "running"
    assert loaded["video_path"] == "/test/video.mp4"
    assert loaded["frame_step"] == 30
    assert loaded["confidence"] == 0.25
    assert len(loaded["results"]) == 1
    
    # Clean up
    conn = _connect()
    conn.execute("DELETE FROM batch_seg_jobs WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()


def test_checkpoint_resume_after_crash():
    """Test that batch segmentation can resume after crash."""
    from services.db import save_batch_seg_checkpoint, load_batch_seg_checkpoint
    
    task_id = "test-resume-task"
    
    # Clean up
    import sqlite3
    from services.db import _connect, init_db
    init_db()
    conn = _connect()
    conn.execute("DELETE FROM batch_seg_jobs WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    
    # Simulate crash at frame 200
    save_batch_seg_checkpoint(task_id, {
        "video_path": "/test/video2.mp4",
        "frame_step": 30,
        "confidence": 0.3,
        "status": "running",
        "last_frame_idx": 200,
        "total_frames": 500,
        "results": [{"frame": i, "objects": []} for i in range(0, 201, 30)]
    })
    
    # Simulate restart - should load checkpoint
    loaded = load_batch_seg_checkpoint(task_id)
    
    assert loaded is not None
    assert loaded["status"] == "running"
    assert loaded["last_frame_idx"] == 200
    
    # Should resume from frame 200, not from 0
    resume_from = loaded["last_frame_idx"]
    assert resume_from == 200
    assert resume_from > 0
    
    # Clean up
    conn = _connect()
    conn.execute("DELETE FROM batch_seg_jobs WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()


def test_checkpoint_overwrite():
    """Test that saving a checkpoint overwrites the previous one."""
    from services.db import save_batch_seg_checkpoint, load_batch_seg_checkpoint
    
    task_id = "test-overwrite-task"
    
    # Clean up
    from services.db import _connect, init_db
    init_db()
    conn = _connect()
    conn.execute("DELETE FROM batch_seg_jobs WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
    
    # Save first checkpoint
    save_batch_seg_checkpoint(task_id, {
        "video_path": "/test/video.mp4",
        "frame_step": 30,
        "confidence": 0.25,
        "status": "running",
        "last_frame_idx": 100,
        "total_frames": 1000,
        "results": []
    })
    
    # Save second checkpoint (should overwrite)
    save_batch_seg_checkpoint(task_id, {
        "video_path": "/test/video.mp4",
        "frame_step": 30,
        "confidence": 0.25,
        "status": "running",
        "last_frame_idx": 200,
        "total_frames": 1000,
        "results": [{"frame": 150}]
    })
    
    # Load and verify last checkpoint
    loaded = load_batch_seg_checkpoint(task_id)
    assert loaded["last_frame_idx"] == 200
    assert len(loaded["results"]) == 1
    
    # Clean up
    conn = _connect()
    conn.execute("DELETE FROM batch_seg_jobs WHERE task_id = ?", (task_id,))
    conn.commit()
    conn.close()
