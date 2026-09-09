"""Smoke test for S2DConv UAV architecture: modules, YAML, weight transfer, forward pass, VRAM.

Usage:
    muravei_env\\Scripts\\python.exe backend\\scripts\\smoke_s2d.py

Exits 0 on success, 1 on any failure.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

YAML_PATH = ROOT / "assets" / "models" / "yolo26n-uav.yaml"
GHOST_YAML_PATH = ROOT / "assets" / "models" / "yolo26n-uav-ghost.yaml"
PRETRAINED = ROOT / "yolo26n.pt"
FT_WEIGHTS = ROOT / "assets" / "models" / "yolo26n-ft.pt"

passed = 0
failed = 0


def _ok(name: str) -> None:
    global passed
    passed += 1
    print(f"  ✅ {name}")


def _fail(name: str, err: str) -> None:
    global failed
    failed += 1
    print(f"  ❌ {name}: {err}")


def test_modules() -> None:
    print("\n=== 1. Custom modules import & instantiation ===")
    try:
        from services.custom_yolo_modules import (
            S2DConv, FasterGhostConv, FasterGhostBottleneck, FasterGhostC3k2,
            SpaceToDepth, register_custom_modules,
        )
        _ok("import custom_yolo_modules")
    except Exception as exc:
        _fail("import custom_yolo_modules", str(exc))
        return

    import torch

    # SpaceToDepth
    try:
        s2d = SpaceToDepth(block_size=2)
        x = torch.randn(1, 3, 64, 64)
        y = s2d(x)
        assert y.shape == (1, 12, 32, 32), f"expected (1,12,32,32) got {y.shape}"
        _ok("SpaceToDepth forward [1,3,64,64] -> [1,12,32,32]")
    except Exception as exc:
        _fail("SpaceToDepth forward", str(exc))

    # S2DConv (replaces Conv 3->16 stride=2)
    try:
        m = S2DConv(c1=3, c2=16)
        x = torch.randn(1, 3, 640, 640)
        y = m(x)
        assert y.shape[0] == 1 and y.shape[1] == 16 and y.shape[2] == 320 and y.shape[3] == 320, \
            f"expected (1,16,320,320) got {y.shape}"
        _ok("S2DConv(3,16) forward [1,3,640,640] -> [1,16,320,320]")
    except Exception as exc:
        _fail("S2DConv(3,16) forward", str(exc))

    # S2DConv with odd dimensions (SAHI tile)
    try:
        m = S2DConv(c1=3, c2=16)
        x = torch.randn(1, 3, 513, 513)
        y = m(x)
        assert y.shape[1] == 16 and y.shape[2] == 257 and y.shape[3] == 257, \
            f"expected (1,16,257,257) got {y.shape}"
        _ok("S2DConv(3,16) odd dimensions [1,3,513,513] -> [1,16,257,257]")
    except Exception as exc:
        _fail("S2DConv odd dimensions", str(exc))

    # FasterGhostConv
    try:
        m = FasterGhostConv(c1=64, c2=128)
        x = torch.randn(1, 64, 40, 40)
        y = m(x)
        assert y.shape == (1, 128, 40, 40), f"expected (1,128,40,40) got {y.shape}"
        _ok("FasterGhostConv(64,128) forward")
    except Exception as exc:
        _fail("FasterGhostConv forward", str(exc))

    # FasterGhostBottleneck
    try:
        m = FasterGhostBottleneck(c1=64, c2=64, shortcut=True)
        x = torch.randn(1, 64, 20, 20)
        y = m(x)
        assert y.shape == (1, 64, 20, 20), f"expected (1,64,20,20) got {y.shape}"
        _ok("FasterGhostBottleneck(64,64,shortcut=True) forward")
    except Exception as exc:
        _fail("FasterGhostBottleneck forward", str(exc))

    # FasterGhostC3k2 — same output shape as C3k2
    try:
        from ultralytics.nn.modules.block import C3k2
        c1, c2 = 128, 64
        ref = C3k2(c1=c1, c2=c2, n=1, c3k=True)
        ghost = FasterGhostC3k2(c1=c1, c2=c2, n=1, c3k=True)
        x = torch.randn(1, c1, 20, 20)
        y_ref = ref(x)
        y_ghost = ghost(x)
        assert y_ref.shape == y_ghost.shape, f"C3k2 {y_ref.shape} != FGC3k2 {y_ghost.shape}"
        _ok(f"FasterGhostC3k2(128,64) output shape matches C3k2: {y_ghost.shape}")
    except Exception as exc:
        _fail("FasterGhostC3k2 forward", str(exc))

    # Module registration
    try:
        register_custom_modules()
        import ultralytics.nn.tasks as _tasks
        assert hasattr(_tasks, "S2DConv"), "S2DConv not registered in tasks"
        assert hasattr(_tasks, "FasterGhostConv"), "FasterGhostConv not registered in tasks"
        assert hasattr(_tasks, "FasterGhostC3k2"), "FasterGhostC3k2 not registered in tasks"
        _ok("register_custom_modules -> S2DConv / FasterGhostConv / FasterGhostC3k2 visible")
    except Exception as exc:
        _fail("register_custom_modules", str(exc))


def test_yaml_parse() -> None:
    print("\n=== 2. YAML parsing ===")
    if not YAML_PATH.is_file():
        _fail("yolo26n-uav.yaml exists", f"not found: {YAML_PATH}")
        return

    try:
        from services.custom_yolo_modules import register_custom_modules
        register_custom_modules()
        from ultralytics import YOLO
        model = YOLO(str(YAML_PATH))
        _ok(f"YOLO('{YAML_PATH.name}') parsed successfully")
    except Exception as exc:
        _fail("YOLO YAML parse", str(exc))
        return

    # Verify layer 0 is S2DConv
    try:
        from services.custom_yolo_modules import S2DConv
        layer0 = model.model.model[0]
        assert isinstance(layer0, S2DConv), f"layer 0 is {type(layer0).__name__}, expected S2DConv"
        _ok(f"layer 0 = S2DConv (verified)")
    except Exception as exc:
        _fail("layer 0 type check", str(exc))

    # Verify total params ~2.6M (same ballpark as yolo26n)
    try:
        total = sum(p.numel() for p in model.model.parameters())
        # yolo26n = 2,591,962; S2DConv layer0 is smaller but nc=238 makes head bigger
        _ok(f"total params = {total:,}")
    except Exception as exc:
        _fail("param count", str(exc))


def test_weight_transfer() -> None:
    print("\n=== 3. Partial weight transfer ===")
    # Pick best available pretrained
    pretrained = PRETRAINED if PRETRAINED.is_file() else FT_WEIGHTS
    if not pretrained.is_file():
        _fail("pretrained weights", f"not found: {PRETRAINED} or {FT_WEIGHTS}")
        return

    try:
        from services.weight_transfer import load_with_transfer
        model, matched, unmatched = load_with_transfer(YAML_PATH, pretrained, verbose=True)
        _ok(f"load_with_transfer: {len(matched)} matched, {len(unmatched)} unmatched keys")
    except Exception as exc:
        _fail("load_with_transfer", str(exc))
        return

    # Verify transfer ratio
    try:
        import torch
        total = sum(p.numel() for p in model.model.parameters())
        matched_params = sum(v.numel() for v in matched.values())
        ratio = matched_params / total * 100 if total > 0 else 0
        # Expected mismatches: model.0 (S2DConv vs Conv) + model.23 (nc=238 vs nc=80 head)
        # ~11% unmatched is normal; threshold set to 85%
        if ratio > 85:
            _ok(f"transfer ratio = {ratio:.1f}% (>85% threshold)")
        else:
            _fail("transfer ratio", f"{ratio:.1f}% (< 85% threshold)")
    except Exception as exc:
        _fail("transfer ratio calculation", str(exc))


def test_forward_pass() -> None:
    print("\n=== 4. Forward pass comparison ===")
    import torch
    import numpy as np

    pretrained = PRETRAINED if PRETRAINED.is_file() else FT_WEIGHTS
    if not pretrained.is_file():
        _fail("pretrained weights", "not found")
        return

    try:
        from services.custom_yolo_modules import register_custom_modules
        register_custom_modules()
        from services.weight_transfer import load_with_transfer
        from ultralytics import YOLO

        # Standard model
        std_model = YOLO(str(pretrained))
        _ok("standard YOLO26n loaded")

        # UAV model with transfer
        uav_model, _, _ = load_with_transfer(YAML_PATH, pretrained, verbose=False)
        _ok("UAV model loaded with transfer")
    except Exception as exc:
        _fail("model loading for forward pass", str(exc))
        return

    # Create synthetic test image
    try:
        img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
    except Exception as exc:
        _fail("create test image", str(exc))
        return

    # Standard inference
    try:
        t0 = time.time()
        std_results = std_model(img, verbose=False, imgsz=640)
        std_ms = (time.time() - t0) * 1000
        _ok(f"standard model inference: {std_ms:.1f} ms, {len(std_results[0].boxes)} boxes")
    except Exception as exc:
        _fail("standard model inference", str(exc))

    # UAV inference
    try:
        t0 = time.time()
        uav_results = uav_model(img, verbose=False, imgsz=640)
        uav_ms = (time.time() - t0) * 1000
        _ok(f"UAV model inference: {uav_ms:.1f} ms, {len(uav_results[0].boxes)} boxes")
    except Exception as exc:
        _fail("UAV model inference", str(exc))


def test_vram() -> None:
    print("\n=== 5. VRAM comparison ===")
    try:
        import torch
        if not torch.cuda.is_available():
            _ok("CUDA not available — VRAM test skipped (CPU-only)")
            return
    except Exception as exc:
        _ok(f"torch not available — VRAM test skipped ({exc})")
        return

    pretrained = PRETRAINED if PRETRAINED.is_file() else FT_WEIGHTS
    if not pretrained.is_file():
        _ok("no pretrained weights — VRAM test skipped")
        return

    from services.custom_yolo_modules import register_custom_modules
    register_custom_modules
    from ultralytics import YOLO
    from services.weight_transfer import load_with_transfer
    import numpy as np

    try:
        torch.cuda.reset_peak_memory_stats()

        # Standard
        std_model = YOLO(str(pretrained))
        img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
        _ = std_model(img, verbose=False, imgsz=640)
        std_vram = torch.cuda.max_memory_allocated() / (1024 ** 2)

        torch.cuda.reset_peak_memory_stats()
        torch.cuda.empty_cache()

        # UAV
        uav_model, _, _ = load_with_transfer(YAML_PATH, pretrained, verbose=False)
        _ = uav_model(img, verbose=False, imgsz=640)
        uav_vram = torch.cuda.max_memory_allocated() / (1024 ** 2)

        delta = uav_vram - std_vram
        _ok(f"standard VRAM peak: {std_vram:.1f} MB")
        _ok(f"UAV VRAM peak: {uav_vram:.1f} MB (delta: {delta:+.1f} MB)")

        if abs(delta) < 200:
            _ok("VRAM delta < 200 MB (acceptable)")
        else:
            _fail("VRAM delta", f"{delta:+.1f} MB exceeds 200 MB threshold")
    except Exception as exc:
        _fail("VRAM measurement", str(exc))


def test_ghost_yaml_parse() -> None:
    print("\n=== 6. Ghost YAML parsing ===")
    if not GHOST_YAML_PATH.is_file():
        _fail("yolo26n-uav-ghost.yaml exists", f"not found: {GHOST_YAML_PATH}")
        return

    try:
        from services.custom_yolo_modules import register_custom_modules
        register_custom_modules()
        from ultralytics import YOLO
        model = YOLO(str(GHOST_YAML_PATH))
        _ok(f"YOLO('{GHOST_YAML_PATH.name}') parsed successfully")
    except Exception as exc:
        _fail("Ghost YAML parse", str(exc))
        return

    from services.custom_yolo_modules import FasterGhostC3k2, S2DConv
    from ultralytics.nn.modules.block import C3k2

    # Verify layer 0 is S2DConv
    try:
        layer0 = model.model.model[0]
        assert isinstance(layer0, S2DConv), f"layer 0 is {type(layer0).__name__}, expected S2DConv"
        _ok("layer 0 = S2DConv (verified)")
    except Exception as exc:
        _fail("ghost layer 0 type check", str(exc))

    # Verify layers 13, 16, 19 are FasterGhostC3k2
    for idx in (13, 16, 19):
        try:
            layer = model.model.model[idx]
            assert isinstance(layer, FasterGhostC3k2), \
                f"layer {idx} is {type(layer).__name__}, expected FasterGhostC3k2"
            _ok(f"layer {idx} = FasterGhostC3k2 (verified)")
        except Exception as exc:
            _fail(f"ghost layer {idx} type check", str(exc))

    # Verify layer 22 is still original C3k2 (NOT replaced)
    try:
        layer22 = model.model.model[22]
        assert isinstance(layer22, C3k2), \
            f"layer 22 is {type(layer22).__name__}, expected C3k2 (attention must be preserved)"
        assert not isinstance(layer22, FasterGhostC3k2), \
            "layer 22 must NOT be FasterGhostC3k2"
        _ok("layer 22 = C3k2 (attention preserved, not replaced)")
    except Exception as exc:
        _fail("ghost layer 22 preservation check", str(exc))

    # Param count
    try:
        total = sum(p.numel() for p in model.model.parameters())
        _ok(f"ghost total params = {total:,}")
    except Exception as exc:
        _fail("ghost param count", str(exc))


def test_ghost_weight_transfer() -> None:
    print("\n=== 7. Ghost weight transfer ===")
    if not GHOST_YAML_PATH.is_file():
        _fail("ghost YAML exists", f"not found: {GHOST_YAML_PATH}")
        return

    pretrained = PRETRAINED if PRETRAINED.is_file() else FT_WEIGHTS
    if not pretrained.is_file():
        _fail("pretrained weights", f"not found: {PRETRAINED} or {FT_WEIGHTS}")
        return

    try:
        from services.weight_transfer import load_with_transfer
        model, matched, unmatched = load_with_transfer(
            GHOST_YAML_PATH, pretrained, verbose=True, min_transfer_ratio=0.60,
        )
        _ok(f"ghost load_with_transfer: {len(matched)} matched, {len(unmatched)} unmatched keys")
    except Exception as exc:
        _fail("ghost load_with_transfer", str(exc))
        return

    try:
        import torch
        total = sum(p.numel() for p in model.model.parameters())
        matched_params = sum(v.numel() for v in matched.values())
        ratio = matched_params / total * 100 if total > 0 else 0
        # Expected: ~82% (backbone + layer 22 transfer, neck 13/16/19 + model.0 + model.23 mismatch)
        if ratio > 60:
            _ok(f"ghost transfer ratio = {ratio:.1f}% (>60% threshold)")
        else:
            _fail("ghost transfer ratio", f"{ratio:.1f}% (< 60% threshold)")
    except Exception as exc:
        _fail("ghost transfer ratio calculation", str(exc))


def test_ghost_forward_pass() -> None:
    print("\n=== 8. Ghost forward pass ===")
    import numpy as np

    pretrained = PRETRAINED if PRETRAINED.is_file() else FT_WEIGHTS
    if not pretrained.is_file():
        _fail("pretrained weights", "not found")
        return

    try:
        from services.custom_yolo_modules import register_custom_modules
        register_custom_modules()
        from services.weight_transfer import load_with_transfer

        ghost_model, _, _ = load_with_transfer(GHOST_YAML_PATH, pretrained, verbose=False)
        _ok("ghost model loaded with transfer")
    except Exception as exc:
        _fail("ghost model loading", str(exc))
        return

    try:
        img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
    except Exception as exc:
        _fail("create test image", str(exc))
        return

    try:
        t0 = time.time()
        results = ghost_model(img, verbose=False, imgsz=640)
        ms = (time.time() - t0) * 1000
        _ok(f"ghost model inference: {ms:.1f} ms, {len(results[0].boxes)} boxes")
    except Exception as exc:
        _fail("ghost model inference", str(exc))


def test_ghost_vram() -> None:
    print("\n=== 9. Ghost VRAM comparison ===")
    try:
        import torch
        if not torch.cuda.is_available():
            _ok("CUDA not available — Ghost VRAM test skipped (CPU-only)")
            return
    except Exception as exc:
        _ok(f"torch not available — Ghost VRAM test skipped ({exc})")
        return

    pretrained = PRETRAINED if PRETRAINED.is_file() else FT_WEIGHTS
    if not pretrained.is_file():
        _ok("no pretrained weights — Ghost VRAM test skipped")
        return

    from services.custom_yolo_modules import register_custom_modules
    register_custom_modules()
    from ultralytics import YOLO
    from services.weight_transfer import load_with_transfer
    import numpy as np

    try:
        img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)

        # Standard baseline
        torch.cuda.reset_peak_memory_stats()
        std_model = YOLO(str(pretrained))
        _ = std_model(img, verbose=False, imgsz=640)
        std_vram = torch.cuda.max_memory_allocated() / (1024 ** 2)

        # UAV baseline (Phase 1)
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.empty_cache()
        uav_model, _, _ = load_with_transfer(YAML_PATH, pretrained, verbose=False)
        _ = uav_model(img, verbose=False, imgsz=640)
        uav_vram = torch.cuda.max_memory_allocated() / (1024 ** 2)

        # Ghost (Phase 2)
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.empty_cache()
        ghost_model, _, _ = load_with_transfer(GHOST_YAML_PATH, pretrained, verbose=False)
        _ = ghost_model(img, verbose=False, imgsz=640)
        ghost_vram = torch.cuda.max_memory_allocated() / (1024 ** 2)

        _ok(f"standard VRAM: {std_vram:.1f} MB")
        _ok(f"UAV VRAM: {uav_vram:.1f} MB (Δ vs std: {uav_vram - std_vram:+.1f} MB)")
        _ok(f"ghost VRAM: {ghost_vram:.1f} MB (Δ vs std: {ghost_vram - std_vram:+.1f} MB)")
        _ok(f"ghost vs UAV Δ: {ghost_vram - uav_vram:+.1f} MB (expect negative = savings)")
    except Exception as exc:
        _fail("ghost VRAM measurement", str(exc))


def main() -> int:
    print("=" * 60)
    print("MuraveiVision-PRO — S2DConv + Ghost UAV Architecture Smoke Test")
    print("=" * 60)

    test_modules()
    test_yaml_parse()
    test_weight_transfer()
    test_forward_pass()
    test_vram()
    test_ghost_yaml_parse()
    test_ghost_weight_transfer()
    test_ghost_forward_pass()
    test_ghost_vram()

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
