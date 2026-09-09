"""COCO area-based AP metrics (AP_S / AP_M / AP_L) for air-gap deployment.

Zero external dependencies — reuses Ultralytics internal ap_per_class() for
correct 101-point COCO interpolation and match_predictions() for consistent
IoU matching across 10 thresholds.

COCO area thresholds are computed in ORIGINAL image pixels:
  S:  area < 32²   (drones, camo nets, infantry)
  M:  32² ≤ area < 96²  (mortars, light vehicles, ATGM)
  L:  area ≥ 96²   (tanks, IFVs, helicopters, bunkers)

The COCO-correct methodology: for each size bin, filter GT by area, then
RE-MATCH all predictions against the filtered GT subset. Predictions that
matched GT of a different size count as FP for the current bin.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from ultralytics.utils.metrics import ap_per_class, box_iou
from ultralytics.utils import ops


class UAVSizeMetrics:
    """Autonomous AP_S/AP_M/AP_L calculator for air-gap pipelines.

    Usage:
        1. Call ``store_image(pbatch, predn)`` per image during validation.
        2. Call ``compute(validator)`` once at on_val_end.
        3. Call ``reset()`` to clear buffers (called automatically by compute).
    """

    AREA_BINS = {
        "S": (0, 32**2),
        "M": (32**2, 96**2),
        "L": (96**2, float("inf")),
    }

    def __init__(self) -> None:
        self._per_image: list[dict[str, torch.Tensor | tuple]] = []

    def store_image(self, pbatch: dict, predn: dict) -> None:
        """Save per-image GT + predictions for deferred size-based AP computation.

        Args:
            pbatch: Output of ``DetectionValidator._prepare_batch()``.
                    Expected keys: bboxes (M,4) xyxy resized-px, cls (M,),
                    ori_shape (H,W), imgsz (h,w), ratio_pad (ratio,pad).
            predn:  Output of ``DetectionValidator._prepare_pred()``.
                    Expected keys: bboxes (N,4) xyxy resized-px, conf (N,), cls (N,).
        """
        self._per_image.append(
            {
                "gt_bboxes": pbatch["bboxes"].cpu(),
                "gt_cls": pbatch["cls"].cpu(),
                "ori_shape": pbatch["ori_shape"],
                "ratio_pad": pbatch["ratio_pad"],
                "imgsz": pbatch["imgsz"],
                "pred_bboxes": predn["bboxes"].cpu(),
                "pred_conf": predn["conf"].cpu(),
                "pred_cls": predn["cls"].cpu(),
            }
        )

    def compute(self, validator) -> dict[str, float]:
        """Compute AP_S/AP_M/AP_L with COCO-correct re-matching per size bin.

        Args:
            validator: The DetectionValidator instance (needed for
                       ``match_predictions()`` and ``iouv``).

        Returns:
            Dict with keys: AP_S_50, AP_S, AP_M_50, AP_M, AP_L_50, AP_L.
        """
        results: dict[str, float] = {}

        for bin_name, (min_area, max_area) in self.AREA_BINS.items():
            all_tp: list[np.ndarray] = []
            all_conf: list[np.ndarray] = []
            all_pred_cls: list[np.ndarray] = []
            all_target_cls: list[np.ndarray] = []

            for img in self._per_image:
                gt_bboxes = img["gt_bboxes"]
                gt_cls = img["gt_cls"]
                pred_bboxes = img["pred_bboxes"]
                pred_conf = img["pred_conf"]
                pred_cls = img["pred_cls"]

                n_pred = pred_cls.shape[0]
                n_gt = gt_cls.shape[0]

                # 1. Scale GT bboxes to original pixels → compute areas
                if n_gt > 0:
                    gt_orig = ops.scale_boxes(
                        img["imgsz"],
                        gt_bboxes.clone(),
                        img["ori_shape"],
                        ratio_pad=img["ratio_pad"],
                    )
                    widths = gt_orig[:, 2] - gt_orig[:, 0]
                    heights = gt_orig[:, 3] - gt_orig[:, 1]
                    areas = widths * heights
                else:
                    areas = torch.zeros(0)

                # 2. Filter GT by current size bin
                if n_gt > 0:
                    bin_mask = (areas >= min_area) & (areas < max_area)
                    bin_gt_bboxes = gt_bboxes[bin_mask]
                    bin_gt_cls = gt_cls[bin_mask]
                else:
                    bin_gt_bboxes = gt_bboxes
                    bin_gt_cls = gt_cls

                n_bin_gt = bin_gt_cls.shape[0]

                # 3. Re-match ALL predictions against filtered GT
                if n_bin_gt == 0:
                    # No GT in this bin → all predictions are FP
                    if n_pred > 0:
                        all_tp.append(np.zeros((n_pred, 10), dtype=bool))
                        all_conf.append(pred_conf.numpy())
                        all_pred_cls.append(pred_cls.numpy())
                    continue

                if n_pred == 0:
                    # No predictions → GT targets contribute to recall denominator
                    all_target_cls.append(bin_gt_cls.numpy())
                    continue

                # Compute IoU between filtered GT and ALL predictions
                iou = box_iou(bin_gt_bboxes, pred_bboxes)
                tp = validator.match_predictions(pred_cls, bin_gt_cls, iou).cpu().numpy()

                all_tp.append(tp)
                all_conf.append(pred_conf.numpy())
                all_pred_cls.append(pred_cls.numpy())
                all_target_cls.append(bin_gt_cls.numpy())

            # 4. Concatenate across all images and compute AP
            has_preds = bool(all_tp) or bool(all_conf)
            has_targets = bool(all_target_cls)

            if not has_preds and not has_targets:
                results[f"AP_{bin_name}_50"] = 0.0
                results[f"AP_{bin_name}"] = 0.0
                continue

            tp_cat = np.concatenate(all_tp, axis=0) if all_tp else np.zeros((0, 10), dtype=bool)
            conf_cat = np.concatenate(all_conf, axis=0) if all_conf else np.zeros(0)
            pcls_cat = np.concatenate(all_pred_cls, axis=0) if all_pred_cls else np.zeros(0)
            tcls_cat = np.concatenate(all_target_cls, axis=0) if all_target_cls else np.zeros(0)

            if len(tcls_cat) == 0 or tp_cat.shape[0] == 0:
                results[f"AP_{bin_name}_50"] = 0.0
                results[f"AP_{bin_name}"] = 0.0
                continue

            # ap_per_class returns 12 elements; index 5 = ap array (nc, 10)
            ap_result = ap_per_class(
                tp_cat,
                conf_cat,
                pcls_cat,
                tcls_cat,
                plot=False,
                save_dir=Path(),
                names=None,
            )
            ap = ap_result[5]  # shape (nc, 10)

            results[f"AP_{bin_name}_50"] = float(ap[:, 0].mean()) if ap.shape[0] > 0 else 0.0
            results[f"AP_{bin_name}"] = float(ap.mean()) if ap.size > 0 else 0.0

        self.reset()
        return results

    def reset(self) -> None:
        """Clear stored per-image data."""
        self._per_image = []

    @staticmethod
    def empty_metrics() -> dict[str, float]:
        """Return zeroed metrics dict (6 keys)."""
        return {
            "AP_S_50": 0.0,
            "AP_S": 0.0,
            "AP_M_50": 0.0,
            "AP_M": 0.0,
            "AP_L_50": 0.0,
            "AP_L": 0.0,
        }
