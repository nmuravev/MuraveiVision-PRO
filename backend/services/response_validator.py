"""Response validator — defense-in-depth filter for YOLO/SAHI detections.

Sits in ``YoloEngine._finalize_sync`` after motion/tracking and before the
response envelope. Validates each detection (bbox in [0,1] + ordered, area in
bounds, confidence in range, class_id in enabled catalog), drops invalid ones,
and appends rejections to ``logs/validator_rejections.jsonl`` (one JSON object
per line — safe append, no read-modify-write).

Conventions (match SAHI integration):
- Config: module constants + optional SQLite override via ``get_setting``.
- Types: ``ValidationResult`` dataclass colocated here.
- Logging: ``print("[VALIDATOR] ...")`` (yolo_engine uses print, not logging).
- Graceful degradation: on any validator error, ``validate_batch`` returns the
  original list unchanged — inference never crashes because of validation.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import BASE_DIR
from services.classes import get_class_catalog

# --- Module constants (overridable via SQLite settings) ---
VALIDATOR_ENABLED_DEFAULT = True
MIN_BBOX_AREA_DEFAULT = 0.0001
MAX_BBOX_AREA_DEFAULT = 0.9
MIN_CONFIDENCE_DEFAULT = 0.01
LOG_FILE = BASE_DIR / "logs" / "validator_rejections.jsonl"


@dataclass
class ValidationResult:
    """Result of validating a single detection. Empty reasons == passed."""
    passed: bool
    reasons: list[str] = field(default_factory=list)


def _bool_setting(key: str, default: bool) -> bool:
    try:
        from services.db import get_setting

        val = get_setting(key)
        if val is None:
            return default
        return val == "1" or val.lower() == "true"
    except Exception:  # noqa: BLE001
        return default


def _float_setting(key: str, default: float) -> float:
    try:
        from services.db import get_setting

        val = get_setting(key)
        if val is None:
            return default
        return float(val)
    except Exception:  # noqa: BLE001
        return default


class ResponseValidator:
    """Validates detection dicts before they reach the response envelope."""

    CACHE_TTL_SEC = 300.0

    def __init__(self) -> None:
        self._enabled_ids: set[int] | None = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl: float = self.CACHE_TTL_SEC

    # --- config resolution (SQLite override, fallback to const) ---
    def _enabled(self) -> bool:
        return _bool_setting("validator_enabled", VALIDATOR_ENABLED_DEFAULT)

    def _min_area(self) -> float:
        return _float_setting("validator_min_bbox_area", MIN_BBOX_AREA_DEFAULT)

    def _max_area(self) -> float:
        return _float_setting("validator_max_bbox_area", MAX_BBOX_AREA_DEFAULT)

    def _min_conf(self) -> float:
        return _float_setting("validator_min_confidence", MIN_CONFIDENCE_DEFAULT)

    def _cache_expired(self) -> bool:
        """True if the enabled-ID set must be rebuilt.

        ``_cache_timestamp == 0`` with a populated set is a manual test seed
        (or a cache that was never stamped) — TTL does not evict it.
        """
        if self._enabled_ids is None:
            return True
        if self._cache_timestamp <= 0:
            return False
        return (time.time() - self._cache_timestamp) > self._cache_ttl

    def _reload_catalog_ids(self) -> set[int]:
        return {
            int(item["id"])
            for item in get_class_catalog()
            if item.get("enabled", True)
        }

    # --- catalog cache ---
    def _known_ids(self) -> set[int]:
        """Enabled catalog IDs. On catalog failure keep old cache, else empty set."""
        if not self._cache_expired():
            assert self._enabled_ids is not None
            return self._enabled_ids
        try:
            ids = self._reload_catalog_ids()
        except Exception as exc:  # noqa: BLE001
            print(f"[VALIDATOR] catalog load failed: {exc} — keeping previous known_ids")
            self._cache_timestamp = time.time()
            if self._enabled_ids is not None:
                return self._enabled_ids
            self._enabled_ids = set()
            return self._enabled_ids
        self._enabled_ids = ids
        self._cache_timestamp = time.time()
        return ids

    def refresh_catalog(self) -> None:
        """Invalidate the cached enabled-ID set (call after catalog edits). Immediate."""
        self._enabled_ids = None
        self._cache_timestamp = 0.0

    # --- core checks ---
    def validate_detection(self, detection: dict) -> ValidationResult:
        reasons: list[str] = []
        bbox = detection.get("bbox")
        if not isinstance(bbox, dict):
            return ValidationResult(False, ["bbox missing or not a dict"])

        try:
            x1 = float(bbox.get("x1"))
            y1 = float(bbox.get("y1"))
            x2 = float(bbox.get("x2"))
            y2 = float(bbox.get("y2"))
        except (TypeError, ValueError):
            return ValidationResult(False, ["bbox coordinates missing or non-numeric"])

        for name, v in (("x1", x1), ("y1", y1), ("x2", x2), ("y2", y2)):
            if not (0.0 <= v <= 1.0):
                reasons.append(f"{name}={v} out of [0,1]")
        if x2 <= x1:
            reasons.append(f"x2({x2}) <= x1({x1}) degenerate")
        if y2 <= y1:
            reasons.append(f"y2({y2}) <= y1({y1}) degenerate")

        # area (only meaningful if coords are finite)
        w = max(0.0, x2 - x1)
        h = max(0.0, y2 - y1)
        area = w * h
        if area < self._min_area():
            reasons.append(f"area={area} < min {self._min_area()}")
        if area > self._max_area():
            reasons.append(f"area={area} > max {self._max_area()}")

        # confidence
        try:
            conf = float(detection.get("confidence"))
        except (TypeError, ValueError):
            reasons.append("confidence missing or non-numeric")
            conf = float("nan")
        min_conf = self._min_conf()
        if not (min_conf <= conf <= 1.0):
            reasons.append(f"confidence={conf} out of [{min_conf}, 1.0]")

        # class_id
        class_id = detection.get("class_id")
        try:
            cid = int(class_id)
        except (TypeError, ValueError):
            reasons.append(f"class_id={class_id} not an int")
            cid = -1
        if cid not in self._known_ids():
            reasons.append(f"class_id={cid} not in enabled catalog")

        return ValidationResult(passed=not reasons, reasons=reasons)

    def validate_batch(self, detections: list[dict]) -> list[dict]:
        """Filter to valid detections. Graceful: on error, returns input unchanged."""
        if not self._enabled():
            return detections
        try:
            known = self._known_ids()
            # If catalog failed to load (empty), do not reject everything —
            # skip the class_id check by treating all as known for this batch.
            catalog_ok = bool(known)
            valid: list[dict] = []
            rejected = 0
            for det in detections:
                if not catalog_ok:
                    # catalog unavailable: accept all (graceful)
                    valid.append(det)
                    continue
                res = self.validate_detection(det)
                if res.passed:
                    valid.append(det)
                else:
                    rejected += 1
                    self.log_rejection(det, res.reasons)
            if rejected:
                print(f"[VALIDATOR] rejected {rejected}/{len(detections)} detections")
            return valid
        except Exception as exc:  # noqa: BLE001
            print(f"[VALIDATOR] validate_batch error, passing all through: {exc}")
            return detections

    def log_rejection(self, detection: dict, reasons: list[str]) -> None:
        """Append one JSONL line to logs/validator_rejections.jsonl. Never raises."""
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": time.time(),
                "detection": detection,
                "reasons": reasons,
            }
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception as exc:  # noqa: BLE001
            print(f"[VALIDATOR] log_rejection IO error: {exc}")


_validator: ResponseValidator | None = None


def get_validator() -> ResponseValidator:
    """Module-level singleton (cheap; reused by the engine each frame)."""
    global _validator
    if _validator is None:
        _validator = ResponseValidator()
    return _validator
