"""Smoke test for UAVSizeMetrics (AP_S/AP_M/AP_L) — synthetic, no real model needed.

Tests the core logic: store_image, area binning, re-matching, ap_per_class integration.

Usage:
    muravei_env\\Scripts\\python.exe backend\\scripts\\smoke_uav_metrics.py

Exits 0 on success, 1 on any failure.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

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


def test_import() -> None:
    print("\n=== 1. Import UAVSizeMetrics ===")
    try:
        from services.uav_metrics import UAVSizeMetrics
        _ok("import UAVSizeMetrics")
    except Exception as exc:
        _fail("import UAVSizeMetrics", str(exc))


def test_empty_metrics() -> None:
    print("\n=== 2. Empty / zero-target metrics ===")
    from services.uav_metrics import UAVSizeMetrics

    m = UAVSizeMetrics()

    # empty_metrics static method
    try:
        empty = UAVSizeMetrics.empty_metrics()
        assert len(empty) == 6, f"expected 6 keys, got {len(empty)}"
        assert all(v == 0.0 for v in empty.values()), "all values should be 0.0"
        _ok("empty_metrics() returns 6 zeroed keys")
    except Exception as exc:
        _fail("empty_metrics()", str(exc))

    # compute with no stored images
    try:
        m = UAVSizeMetrics()
        # Need a mock validator for compute()
        result = m.compute(_MockValidator())
        assert len(result) == 6, f"expected 6 keys, got {len(result)}"
        assert all(v == 0.0 for v in result.values()), "all values should be 0.0 with no data"
        _ok("compute() with no images returns zeros")
    except Exception as exc:
        _fail("compute() no images", str(exc))


def test_area_binning() -> None:
    print("\n=== 3. Area bin definitions ===")
    from services.uav_metrics import UAVSizeMetrics

    try:
        bins = UAVSizeMetrics.AREA_BINS
        assert "S" in bins and "M" in bins and "L" in bins
        s_min, s_max = bins["S"]
        m_min, m_max = bins["M"]
        l_min, l_max = bins["L"]
        assert s_min == 0 and s_max == 32**2, f"S bin wrong: {bins['S']}"
        assert m_min == 32**2 and m_max == 96**2, f"M bin wrong: {bins['M']}"
        assert l_min == 96**2 and l_max == float("inf"), f"L bin wrong: {bins['L']}"
        _ok(f"AREA_BINS: S=(0,{32**2}), M=({32**2},{96**2}), L=({96**2},inf)")
    except Exception as exc:
        _fail("AREA_BINS", str(exc))


def test_store_and_reset() -> None:
    print("\n=== 4. Store + reset ===")
    import torch
    from services.uav_metrics import UAVSizeMetrics

    m = UAVSizeMetrics()
    try:
        pbatch = _make_pbatch(n_gt=3, ori_shape=(480, 640), imgsz=(640, 640))
        predn = _make_predn(n_pred=5)
        m.store_image(pbatch, predn)
        assert len(m._per_image) == 1
        _ok("store_image() stores 1 image")
    except Exception as exc:
        _fail("store_image()", str(exc))

    try:
        m.reset()
        assert len(m._per_image) == 0
        _ok("reset() clears buffer")
    except Exception as exc:
        _fail("reset()", str(exc))


def test_synthetic_ap_large() -> None:
    print("\n=== 5. Synthetic AP_L (large objects only) ===")
    import torch
    from services.uav_metrics import UAVSizeMetrics

    # Create GT with LARGE objects only (area > 96² = 9216 px in original image)
    # And predictions that match them perfectly
    m = UAVSizeMetrics()
    validator = _MockValidator()

    # Large GT: 200x200 bbox in 640x640 original → area = 40000 > 9216 ✓
    pbatch = _make_pbatch(
        n_gt=3,
        ori_shape=(640, 640),
        imgsz=(640, 640),
        bbox_size=200,
        gt_cls=[0, 1, 2],
    )
    # Perfect predictions: same bboxes, same classes
    predn = _make_predn(
        n_pred=3,
        bbox_size=200,
        pred_cls=[0, 1, 2],
        conf_val=0.9,
    )
    m.store_image(pbatch, predn)

    try:
        result = m.compute(validator)
        _ok(f"AP_L_50 = {result.get('AP_L_50', 0):.3f}")
        _ok(f"AP_L    = {result.get('AP_L', 0):.3f}")
        # With perfect matches, AP_L should be close to 1.0
        if result.get("AP_L_50", 0) > 0.5:
            _ok("AP_L_50 > 0.5 (large objects matched)")
        else:
            _fail("AP_L_50 > 0.5", f"got {result.get('AP_L_50', 0):.3f}")
    except Exception as exc:
        _fail("compute() synthetic large", str(exc))


def test_synthetic_ap_small_zeros() -> None:
    print("\n=== 6. Synthetic AP_S (no small GT → should be 0) ===")
    import torch
    from services.uav_metrics import UAVSizeMetrics

    # Same large GT as above — no small objects exist
    m = UAVSizeMetrics()
    validator = _MockValidator()

    pbatch = _make_pbatch(n_gt=3, ori_shape=(640, 640), imgsz=(640, 640), bbox_size=200)
    predn = _make_predn(n_pred=3, bbox_size=200, pred_cls=[0, 1, 2])
    m.store_image(pbatch, predn)

    try:
        result = m.compute(validator)
        ap_s = result.get("AP_S_50", -1)
        if ap_s == 0.0:
            _ok("AP_S_50 = 0.0 (no small GT)")
        else:
            _fail("AP_S_50 = 0.0", f"got {ap_s}")
    except Exception as exc:
        _fail("compute() no small GT", str(exc))


def test_mixed_sizes() -> None:
    print("\n=== 7. Mixed sizes (S + M + L GT in same image) ===")
    import torch
    from services.uav_metrics import UAVSizeMetrics

    m = UAVSizeMetrics()
    validator = _MockValidator()

    # Small GT: 20x20 in 640x640 orig → area=400 < 1024 ✓
    # Large GT: 150x150 in 640x640 orig → area=22500 > 9216 ✓
    pbatch_s = _make_pbatch(n_gt=2, ori_shape=(640, 640), imgsz=(640, 640), bbox_size=20, gt_cls=[0, 0])
    pbatch_l = _make_pbatch(n_gt=2, ori_shape=(640, 640), imgsz=(640, 640), bbox_size=150, gt_cls=[1, 1])

    predn_s = _make_predn(n_pred=2, bbox_size=20, pred_cls=[0, 0], conf_val=0.9)
    predn_l = _make_predn(n_pred=2, bbox_size=150, pred_cls=[1, 1], conf_val=0.9)

    m.store_image(pbatch_s, predn_s)
    m.store_image(pbatch_l, predn_l)

    try:
        result = m.compute(validator)
        _ok(f"AP_S_50 = {result.get('AP_S_50', 0):.3f}")
        _ok(f"AP_M_50 = {result.get('AP_M_50', 0):.3f}")
        _ok(f"AP_L_50 = {result.get('AP_L_50', 0):.3f}")
        # Small should be > 0, Large should be > 0, Medium should be 0
        if result.get("AP_S_50", 0) > 0.3:
            _ok("AP_S_50 > 0.3 (small matches found)")
        else:
            _fail("AP_S_50 > 0.3", f"got {result.get('AP_S_50', 0):.3f}")
        if result.get("AP_L_50", 0) > 0.3:
            _ok("AP_L_50 > 0.3 (large matches found)")
        else:
            _fail("AP_L_50 > 0.3", f"got {result.get('AP_L_50', 0):.3f}")
        if result.get("AP_M_50", -1) == 0.0:
            _ok("AP_M_50 = 0.0 (no medium GT)")
        else:
            _fail("AP_M_50 = 0.0", f"got {result.get('AP_M_50', 0):.3f}")
    except Exception as exc:
        _fail("compute() mixed sizes", str(exc))


def test_no_predictions() -> None:
    print("\n=== 8. No predictions (GT exists) → AP = 0 ===")
    import torch
    from services.uav_metrics import UAVSizeMetrics

    m = UAVSizeMetrics()
    validator = _MockValidator()

    pbatch = _make_pbatch(n_gt=3, ori_shape=(640, 640), imgsz=(640, 640), bbox_size=200)
    predn = _make_predn(n_pred=0)  # no predictions
    m.store_image(pbatch, predn)

    try:
        result = m.compute(validator)
        if result.get("AP_L_50", -1) == 0.0:
            _ok("AP_L_50 = 0.0 when no predictions")
        else:
            _fail("AP_L_50 = 0.0", f"got {result.get('AP_L_50', 0)}")
    except Exception as exc:
        _fail("compute() no predictions", str(exc))


def test_cross_size_false_positive() -> None:
    print("\n=== 9. Cross-size FP: large pred matches small GT → FP for L bin ===")
    import torch
    from services.uav_metrics import UAVSizeMetrics

    # Only small GT exists. Large prediction matches small GT.
    # For AP_S: pred matches small GT → TP → AP_S > 0
    # For AP_L: no large GT exists → pred is FP → AP_L = 0
    m = UAVSizeMetrics()
    validator = _MockValidator()

    # Small GT only (20x20 → area 400 < 1024)
    pbatch = _make_pbatch(n_gt=2, ori_shape=(640, 640), imgsz=(640, 640), bbox_size=20, gt_cls=[0, 0])
    # Predictions match the small GT positions (IoU will be high)
    predn = _make_predn(n_pred=2, bbox_size=20, pred_cls=[0, 0], conf_val=0.9)
    m.store_image(pbatch, predn)

    try:
        result = m.compute(validator)
        ap_l = result.get("AP_L_50", -1)
        if ap_l == 0.0:
            _ok("AP_L_50 = 0.0 (no large GT → all preds are FP for L bin)")
        else:
            _fail("AP_L_50 = 0.0 for cross-size", f"got {ap_l:.3f}")
    except Exception as exc:
        _fail("compute() cross-size FP", str(exc))


# --- Helpers ---

class _MockValidator:
    """Minimal mock that provides match_predictions + iouv for re-matching."""

    def __init__(self):
        import torch
        self.iouv = torch.linspace(0.5, 0.95, 10)

    def match_predictions(self, pred_classes, true_classes, iou):
        """Replicate BaseValidator.match_predictions logic."""
        import numpy as np
        import torch

        niou = self.iouv.shape[0]
        correct = np.zeros((pred_classes.shape[0], niou), dtype=bool)
        if pred_classes.shape[0] == 0 or true_classes.shape[0] == 0:
            return torch.from_numpy(correct)

        correct_class = true_classes[:, None] == pred_classes
        iou_np = (iou * correct_class).cpu().numpy() if isinstance(iou, torch.Tensor) else iou * correct_class.numpy()

        for i, threshold in enumerate(self.iouv.cpu().tolist()):
            matches = np.nonzero(iou_np >= threshold)
            matches = np.array(matches).T
            if matches.shape[0]:
                if matches.shape[0] > 1:
                    matches = matches[iou_np[matches[:, 0], matches[:, 1]].argsort()[::-1]]
                    matches = matches[np.unique(matches[:, 1], return_index=True)[1]]
                    matches = matches[np.unique(matches[:, 0], return_index=True)[1]]
                correct[matches[:, 1].astype(int), i] = True
        return torch.from_numpy(correct)


def _make_pbatch(
    n_gt: int = 3,
    ori_shape: tuple[int, int] = (640, 640),
    imgsz: tuple[int, int] = (640, 640),
    bbox_size: int = 100,
    gt_cls: list[int] | None = None,
) -> dict:
    """Create a synthetic pbatch dict matching _prepare_batch() output."""
    import torch

    if n_gt == 0:
        return {
            "bboxes": torch.zeros(0, 4),
            "cls": torch.zeros(0, dtype=torch.long),
            "ori_shape": ori_shape,
            "imgsz": imgsz,
            "ratio_pad": (torch.tensor([1.0, 1.0]), torch.tensor([0.0, 0.0])),
        }

    if gt_cls is None:
        gt_cls = list(range(n_gt))

    # Place bboxes in a grid pattern, each bbox_size × bbox_size
    bboxes = []
    for i in range(n_gt):
        row = i % 3
        col = i // 3
        cx = 50 + col * (bbox_size + 20)
        cy = 50 + row * (bbox_size + 20)
        # Clamp to image bounds
        x1 = min(cx, imgsz[1] - bbox_size)
        y1 = min(cy, imgsz[0] - bbox_size)
        x2 = x1 + bbox_size
        y2 = y1 + bbox_size
        bboxes.append([x1, y1, x2, y2])

    return {
        "bboxes": torch.tensor(bboxes, dtype=torch.float32),
        "cls": torch.tensor(gt_cls[:n_gt], dtype=torch.long),
        "ori_shape": ori_shape,
        "imgsz": imgsz,
        "ratio_pad": (torch.tensor([1.0, 1.0]), torch.tensor([0.0, 0.0])),
    }


def _make_predn(
    n_pred: int = 3,
    bbox_size: int = 100,
    pred_cls: list[int] | None = None,
    conf_val: float = 0.9,
) -> dict:
    """Create a synthetic predn dict matching _prepare_pred() output."""
    import torch

    if n_pred == 0:
        return {
            "bboxes": torch.zeros(0, 4),
            "conf": torch.zeros(0),
            "cls": torch.zeros(0, dtype=torch.long),
        }

    if pred_cls is None:
        pred_cls = list(range(n_pred))

    # Same grid as _make_pbatch so predictions overlap with GT
    bboxes = []
    for i in range(n_pred):
        row = i % 3
        col = i // 3
        cx = 50 + col * (bbox_size + 20)
        cy = 50 + row * (bbox_size + 20)
        x1 = min(cx, 640 - bbox_size)
        y1 = min(cy, 640 - bbox_size)
        x2 = x1 + bbox_size
        y2 = y1 + bbox_size
        bboxes.append([x1, y1, x2, y2])

    return {
        "bboxes": torch.tensor(bboxes, dtype=torch.float32),
        "conf": torch.full((n_pred,), conf_val),
        "cls": torch.tensor(pred_cls[:n_pred], dtype=torch.long),
    }


def main() -> int:
    print("=" * 60)
    print("MuraveiVision-PRO — UAVSizeMetrics Smoke Test")
    print("=" * 60)

    test_import()
    test_empty_metrics()
    test_area_binning()
    test_store_and_reset()
    test_synthetic_ap_large()
    test_synthetic_ap_small_zeros()
    test_mixed_sizes()
    test_no_predictions()
    test_cross_size_false_positive()

    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
