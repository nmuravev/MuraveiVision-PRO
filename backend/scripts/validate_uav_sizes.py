"""Standalone post-training AP_S/AP_M/AP_L validation script.

Computes COCO area-based AP metrics for a trained YOLO model without
any external dependencies beyond Ultralytics.

Usage:
    muravei_env\\Scripts\\python.exe backend\\scripts\\validate_uav_sizes.py ^
        --weights assets/models/yolo26n-ft.pt ^
        --data cache/train_run/dataset/dataset.yaml

    # With custom architecture:
    muravei_env\\Scripts\\python.exe backend\\scripts\\validate_uav_sizes.py ^
        --weights assets/models/yolo26n-ft.pt ^
        --data cache/train_run/dataset/dataset.yaml ^
        --ghost

Exits 0 on success, 1 on error.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="UAV AP_S/AP_M/AP_L post-training validator (air-gap compatible)"
    )
    parser.add_argument(
        "--weights",
        type=str,
        required=True,
        help="Path to trained .pt weights",
    )
    parser.add_argument(
        "--data",
        type=str,
        required=True,
        help="Path to dataset YAML (data.yaml / dataset.yaml)",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Inference image size (default: 640)",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=4,
        help="Validation batch size (default: 4)",
    )
    parser.add_argument(
        "--ghost",
        action="store_true",
        help="Use S2DConv + Ghost neck architecture (Phase 2)",
    )
    parser.add_argument(
        "--uav",
        action="store_true",
        help="Use S2DConv UAV architecture (Phase 1)",
    )
    parser.add_argument(
        "--base",
        type=str,
        default=None,
        help="Base pretrained weights for partial transfer (ghost/uav mode)",
    )
    args = parser.parse_args()

    weights = Path(args.weights)
    data = Path(args.data)

    if not weights.is_file():
        print(f"❌ Weights not found: {weights}")
        return 1
    if not data.is_file():
        print(f"❌ Dataset YAML not found: {data}")
        return 1

    # Register custom modules (S2DConv, FasterGhostC3k2)
    try:
        from services.custom_yolo_modules import register_custom_modules

        register_custom_modules()
        print("✅ Custom modules registered")
    except Exception as exc:
        print(f"⚠️  Custom module registration skipped: {exc}")

    # Load model
    from ultralytics import YOLO

    if args.ghost or args.uav:
        base_path = args.base or str(weights)
        from services.weight_transfer import load_with_transfer

        yaml_name = "yolo26n-uav-ghost.yaml" if args.ghost else "yolo26n-uav.yaml"
        yaml_path = ROOT / "assets" / "models" / yaml_name

        if not yaml_path.is_file():
            print(f"❌ YAML not found: {yaml_path}")
            return 1

        print(f"Loading {yaml_name} with transfer from {base_path}…")
        model, matched, unmatched = load_with_transfer(yaml_path, base_path, verbose=True)
        print(f"  Transfer: {len(matched)} matched, {len(unmatched)} skipped")
    else:
        print(f"Loading model: {weights.name}…")
        model = YOLO(str(weights))

    # Register UAV size-AP callbacks
    from services.trainer import _register_uav_size_callbacks

    _register_uav_size_callbacks(model)
    print("✅ UAV size-AP callbacks registered")

    # Run validation
    print(f"\n{'='*60}")
    print(f"UAV Size-AP Validation")
    print(f"  Weights:  {weights.name}")
    print(f"  Dataset:  {data.name}")
    print(f"  imgsz:    {args.imgsz}")
    print(f"{'='*60}\n")

    t0 = time.time()
    try:
        results = model.val(
            data=str(data),
            imgsz=args.imgsz,
            batch=args.batch,
            plots=False,
            save_json=False,
            verbose=True,
        )
    except Exception as exc:
        print(f"❌ Validation failed: {exc}")
        return 1

    elapsed = time.time() - t0
    print(f"\n{'='*60}")
    print(f"Validation completed in {elapsed:.1f}s")

    # Print standard metrics if available
    if isinstance(results, dict):
        map50 = results.get("metrics/mAP50(B)", None)
        map5095 = results.get("metrics/mAP50-95(B)", None)
        if map50 is not None:
            print(f"  mAP@50:     {map50:.4f}")
        if map5095 is not None:
            print(f"  mAP@50-95:  {map5095:.4f}")

    print(f"\n  Size-AP metrics are logged above (UAV size-AP line).")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
