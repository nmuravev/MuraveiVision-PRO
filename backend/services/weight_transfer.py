"""Partial weight transfer from pretrained YOLO26n to custom UAV architecture.

Builds model from custom YAML, then loads all compatible weights from
the pretrained checkpoint via strict=False.

Phase 1 (S2DConv only): ~89.5% transfer — model.0 + model.23 mismatched.
Phase 2 (S2D + Ghost neck): ~82% transfer — model.0 + model.13/16/19 + model.23 mismatched.
Backbone (model.1–10) and layer 22 (C3k2 attn) always transfer at 100%.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import torch

from services.custom_yolo_modules import register_custom_modules


def load_with_transfer(
    yaml_path: str | Path,
    pretrained_path: str | Path,
    nc: int = 238,
    verbose: bool = True,
    min_transfer_ratio: float = 0.60,
) -> tuple[Any, dict[str, torch.Tensor], list[str]]:
    """Build model from custom YAML and load matching pretrained weights.

    Args:
        yaml_path: Path to custom YAML (e.g. assets/models/yolo26n-uav-ghost.yaml).
        pretrained_path: Path to pretrained .pt weights (e.g. yolo26n.pt).
        nc: Number of classes for the new model.
        verbose: Print transfer statistics.
        min_transfer_ratio: Warn if matched params fall below this fraction (0.60 = 60%).

    Returns:
        (model, matched_state_dict, unmatched_keys)
    """
    from ultralytics import YOLO

    # Register custom modules so parse_model() can resolve YAML tokens
    register_custom_modules()

    model = YOLO(str(yaml_path))
    model_sd = model.model.state_dict()

    # Load pretrained state dict
    ckpt = torch.load(str(pretrained_path), map_location="cpu", weights_only=False)

    # Ultralytics .pt checkpoints store the full DetectionModel under 'model' key
    if isinstance(ckpt, dict) and "model" in ckpt:
        pretrained_obj = ckpt["model"]
        if hasattr(pretrained_obj, "state_dict"):
            pretrained_sd = pretrained_obj.state_dict()
        elif isinstance(pretrained_obj, dict):
            pretrained_sd = pretrained_obj
        else:
            pretrained_sd = {}
    elif isinstance(ckpt, dict) and any(k.startswith("model.") for k in ckpt):
        pretrained_sd = ckpt
    else:
        pretrained_sd = {}

    matched: dict[str, torch.Tensor] = {}
    unmatched: list[str] = []

    for k, v in pretrained_sd.items():
        if k in model_sd and v.shape == model_sd[k].shape:
            matched[k] = v
        else:
            unmatched.append(k)

    # Load matched weights (strict=False skips mismatched keys)
    model.model.load_state_dict(matched, strict=False)

    total_model_params = sum(v.numel() for v in model_sd.values())
    matched_params = sum(v.numel() for v in matched.values())

    if verbose:
        total_pretrained = len(pretrained_sd)
        total_model = len(model_sd)
        matched_count = len(matched)
        print(f"[WEIGHT-TRANSFER] pretrained={total_pretrained} keys, model={total_model} keys")
        print(f"[WEIGHT-TRANSFER] matched={matched_count} keys "
              f"({matched_params:,}/{total_model_params:,} params = "
              f"{matched_params/total_model_params*100:.2f}%)")
        if unmatched:
            # Group unmatched by layer prefix
            prefixes: dict[str, int] = {}
            for k in unmatched:
                prefix = k.split(".")[0] + "." + k.split(".")[1]
                prefixes[prefix] = prefixes.get(prefix, 0) + 1
            print(f"[WEIGHT-TRANSFER] unmatched={len(unmatched)} keys, by layer:")
            for prefix, count in sorted(prefixes.items()):
                print(f"  {prefix}: {count} keys")

    ratio = matched_params / total_model_params if total_model_params > 0 else 0
    if ratio < min_transfer_ratio:
        print(f"[WEIGHT-TRANSFER] WARNING: transfer ratio {ratio:.1%} below threshold "
              f"{min_transfer_ratio:.0%}. Backbone should still be 100% — neck trains from scratch.")

    return model, matched, unmatched
