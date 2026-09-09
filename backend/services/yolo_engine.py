"""YOLO26 / YOLOE-26 detection engine: one Ultralytics model, one GPU queue."""
from __future__ import annotations

from services.ultralytics_airgap import ensure_ultralytics_airgap

ensure_ultralytics_airgap()

import asyncio
import io
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import BASE_DIR
from services.classes import (
    canonical_label,
    class_id_for_name,
    confidence_threshold_for,
    is_catalog_label,
    is_scene_class,
    live_prompt_names,
    minimum_confidence_threshold,
    to_snake_case,
)

IMGSZ = 1024
DEFAULT_CONF = 0.25
# Near-full-frame only (trenches / roads on LBS can exceed 12% of the image).
MAX_SCENE_AREA = 0.55
QUEUE_MAX = 4
NMS_IOU = 0.45
TILE_OVERLAP = 0.18
COCO_FALLBACK_CONF = 0.35
# CLIP matches mines/tripwires to grass/dirt; require a high score if they appear.
_STRICT_TOKENS = ("mine", "tripwire", "booby")
_STRICT_CONF = 0.55
_DRONE_CONF = 0.35
# Aerial LBS fortification cues are often low-confidence at 100m+ — keep soft floor.
_LBS_SOFT_TOKENS = (
    "trench",
    "foxhole",
    "barbed",
    "footpath",
    "crater",
    "scorch",
    "tire track",
    "wreck",
    "ditch",
    "obstacle",
    "berm",
    "sandbag",
    "bottle",
    "litter",
    "garbage",
    "plastic",
    "wrapper",
    "dug",
    "disturb",
    "spoil",
    "can",
)
_LBS_SOFT_CONF = 0.12

# Closed-set YOLO26 COCO clutter (plus any label not in military YAML after alias).
_COCO_DROP = (
    "frisbee",
    "sports_ball",
    "sports ball",
    "dog",
    "cat",
    "horse",
    "sheep",
    "cow",
    "umbrella",
    "handbag",
    "suitcase",
    "skis",
    "snowboard",
    "skateboard",
    "surfboard",
    "tennis",
    "bottle",
    "cup",
    "chair",
    "bench",
    "tv",
    "laptop",
    "cell phone",
    "cell_phone",
    "keyboard",
    "mouse",
    "remote",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
    "stop sign",
    "parking meter",
    "traffic light",
    "fire hydrant",
    "potted plant",
    "dining table",
    "toilet",
    "sink",
    "refrigerator",
    "microwave",
    "oven",
    "toaster",
    "couch",
    "bed",
    "wine glass",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "tie",
    "backpack",
)

_BOX_COLORS = (
    "#ef4444",
    "#f97316",
    "#eab308",
    "#22c55e",
    "#06b6d4",
    "#3b82f6",
    "#a855f7",
    "#ec4899",
    "#84cc16",
    "#14b8a6",
    "#f43f5e",
    "#64748b",
)

def _is_osd_box(bbox: dict[str, float]) -> bool:
    """Drop HUD / watermark / ticker boxes (corners and bottom banner)."""
    x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
    w, h = max(1e-6, x2 - x1), max(1e-6, y2 - y1)
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    if y1 >= 0.72 and w >= 0.10:
        return True
    if y2 <= 0.14 and (x1 <= 0.22 or x2 >= 0.78) and w * h < 0.08:
        return True
    if cy >= 0.78 and cx <= 0.42:
        return True
    if w / h >= 4.2:
        return True
    if x1 <= 0.02 and y2 >= 0.85:
        return True
    return False


def _keep_live_label(name: str) -> bool:
    """Keep only military-catalog labels; drop COCO clutter and unmapped names (train, boat, …)."""
    blob = (name or "").lower().replace("-", " ").replace("_", " ")
    if any(tok in blob for tok in _COCO_DROP):
        return False
    return is_catalog_label(name)

WEIGHTS_DIR = BASE_DIR / "runs" / "detect" / "train" / "weights"
CLIP_MIN_BYTES = 200 * 1024 * 1024


def _box_area(bbox: dict[str, float]) -> float:
    return max(0.0, bbox["x2"] - bbox["x1"]) * max(0.0, bbox["y2"] - bbox["y1"])


def _box_iou(a: dict[str, float], b: dict[str, float]) -> float:
    ax1, ay1, ax2, ay2 = a["x1"], a["y1"], a["x2"], a["y2"]
    bx1, by1, bx2, by2 = b["x1"], b["y1"], b["x2"], b["y2"]
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = _box_area(a) + _box_area(b) - inter
    return inter / union if union > 0 else 0.0


def _contains(outer: dict[str, float], inner: dict[str, float], pad: float = 0.01) -> bool:
    return (
        outer["x1"] - pad <= inner["x1"]
        and outer["y1"] - pad <= inner["y1"]
        and outer["x2"] + pad >= inner["x2"]
        and outer["y2"] + pad >= inner["y2"]
    )


def _drop_outer_boxes(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop a large box that fully contains a smaller different-class object."""
    kept: list[dict[str, Any]] = []
    for i, obj in enumerate(objects):
        bbox = obj["bbox"]
        area = _box_area(bbox)
        swallows = False
        for j, other in enumerate(objects):
            if i == j:
                continue
            other_box = other["bbox"]
            other_area = _box_area(other_box)
            if other_area <= 0 or area < other_area * 3:
                continue
            if _contains(bbox, other_box) and obj.get("class_en") != other.get("class_en"):
                swallows = True
                break
        if not swallows:
            kept.append(obj)
    kept.sort(key=lambda o: _box_area(o["bbox"]), reverse=True)
    return kept


def _clip_ready() -> bool:
    """YOLOE text prompting needs CLIP + mobileclip2_b.ts (~242 MB)."""
    try:
        import clip  # noqa: F401
    except ImportError:
        return False
    for path in (
        BASE_DIR / "mobileclip2_b.ts",
        Path.cwd() / "mobileclip2_b.ts",
        WEIGHTS_DIR / "mobileclip2_b.ts",
    ):
        if path.exists() and path.stat().st_size > CLIP_MIN_BYTES:
            return True
    return False


@dataclass
class _InferJob:
    image_bytes: bytes
    confidence: float
    frame_idx: int
    time_sec: float
    viewer_id: str
    future: asyncio.Future
    use_sahi: bool = False
    slice_height: int = 512
    slice_width: int = 512
    overlap_ratio: float = 0.2


class YoloEngine:
    def __init__(self) -> None:
        self.model = None
        self.model_name = ""
        self.model_path: Path | None = None
        self.mode = "offline"
        self.kind = "none"
        self._names: dict[int, str] = {}
        self._queue: asyncio.Queue[_InferJob] | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._fallback = None
        self._device = "cpu"
        self._device_backend = "cpu"
        self._ort_providers: list[str] = []
        self._cuda_name = ""
        self._degraded = False
        self._tier = "unknown"
        self._imgsz = IMGSZ
        self._last_inference_ms: int | None = None
        self._last_n: int = 0
        self._last_nms_mode: str = "native"
        self._last_used_kind: str = "none"
        self._init_error_ru: str = ""
        self._motion_states: dict[str, Any] = {}
        self._trackers: dict[str, Any] = {}
        self._load()
        self._detect_device()

    def engine_status(self) -> str:
        """Unified vocabulary: offline | cpu | directml | cuda."""
        from config import (
            ENGINE_STATUS_CPU,
            ENGINE_STATUS_CUDA,
            ENGINE_STATUS_DIRECTML,
            ENGINE_STATUS_OFFLINE,
        )

        if self.mode in ("offline", "error") or self.model is None:
            return ENGINE_STATUS_OFFLINE
        backend = str(getattr(self, "_device_backend", "cpu") or "cpu")
        if backend in ("torch-cuda",) or str(self._device).startswith("cuda"):
            return ENGINE_STATUS_CUDA
        if backend == "directml" or getattr(self, "_use_directml", False):
            return ENGINE_STATUS_DIRECTML
        return ENGINE_STATUS_CPU

    def _weight_candidates(self) -> list[Path]:
        """Tactical ladder l-ft > m-ft > s-ft > n-ft > n under assets/models (Z1)."""
        from config import MODELS_DIR, TACTICAL_WEIGHT_LADDER, resolve_default_detect_weight

        ordered: list[Path] = []
        seen: set[str] = set()
        primary = resolve_default_detect_weight(MODELS_DIR)
        if primary is not None:
            ordered.append(primary)
            seen.add(primary.name.lower())
        for name in TACTICAL_WEIGHT_LADDER:
            key = name.lower()
            if key in seen:
                continue
            path = MODELS_DIR / name
            ordered.append(path)
            seen.add(key)
        # Secondary: runs/detect copies of the same ladder names only (no COCO dump).
        for name in TACTICAL_WEIGHT_LADDER:
            path = WEIGHTS_DIR / name
            key = path.name.lower()
            if key in seen:
                continue
            ordered.append(path)
            seen.add(key)
        return ordered

    def force_load(self, weights: Path) -> bool:
        """Hard-switch active weights (e.g. after finetune promote)."""
        if not weights.is_file() or weights.stat().st_size <= 1024:
            print(f"[YOLO] force_load missing: {weights}")
            return False
        try:
            self.model = None
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:  # noqa: BLE001
                pass
            if not self._try_load(weights):
                return False
            self.model_name = weights.name
            self.model_path = weights
            self.mode = "ready"
            sample = list(self._names.items())[:8]
            print(f"[YOLO] force_load ok: {weights} kind={self.kind} nc={len(self._names)} sample={sample}")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[YOLO] force_load failed {weights.name}: {exc}")
            self.model = None
            self.kind = "none"
            self._names = {}
            self.mode = "error"
            return False

    def _cache_names(self) -> None:
        names = getattr(self.model, "names", {}) or {}
        if isinstance(names, dict):
            self._names = {int(k): str(v) for k, v in names.items()}
        elif isinstance(names, (list, tuple)):
            self._names = {i: str(v) for i, v in enumerate(names)}
        else:
            self._names = {}

    def _label(self, class_id: int, result_names: Any = None) -> str:
        names = result_names if result_names is not None else self._names
        raw = ""
        if isinstance(names, dict):
            raw = str(names.get(class_id, names.get(str(class_id), "")) or "")
        elif isinstance(names, (list, tuple)) and 0 <= class_id < len(names):
            raw = str(names[class_id])
        snake = to_snake_case(raw) if raw else ""
        if snake and snake != str(class_id):
            return snake
        return f"class_{int(class_id)}"

    def _load_yoloe_text(self, weights: Path) -> bool:
        """Text-prompted YOLOE-26: set_classes(YAML names). See ultralytics YOLOE API."""
        try:
            from ultralytics import YOLOE
        except ImportError:
            print("[YOLO] ultralytics.YOLOE not available")
            return False
        prompts = live_prompt_names()
        if not prompts:
            return False
        if not _clip_ready():
            print("[YOLO] YOLOE text needs CLIP + mobileclip2_b.ts — skip until encoder is on disk")
            return False
        model = YOLOE(str(weights))
        model.set_classes(prompts)
        self.model = model
        self.kind = "yoloe-text"
        self._cache_names()
        print(f"[YOLO] YOLOE live prompts: {len(prompts)} {prompts[:8]}...")
        return True

    def _load_yoloe_pf(self, weights: Path) -> bool:
        try:
            from ultralytics import YOLOE
        except ImportError:
            return False
        self.model = YOLOE(str(weights))
        self.kind = "yoloe-pf"
        self._cache_names()
        print("[YOLO] YOLOE prompt-free checkpoint (built-in vocabulary)")
        return True

    def _load_yolo26(self, weights: Path) -> bool:
        from ultralytics import YOLO

        self.model = YOLO(str(weights))
        self.kind = "yolo26-closed"
        self._cache_names()
        print("[YOLO] Closed-set YOLO26 — labels from model.names, not YAML index")
        return True

    def _try_load(self, weights: Path) -> bool:
        name = weights.name.lower()
        if "yoloe" in name and name.endswith("-pf.pt"):
            return self._load_yoloe_pf(weights)
        if "yoloe" in name:
            return self._load_yoloe_text(weights)
        if "seg" in name:
            print(f"[YOLO] Skipping segment-only weights for unsupported path: {weights.name}")
            return False
        if "yolo26" in name or name in ("best.pt", "last.pt", "finetuned-detect.pt"):
            return self._load_yolo26(weights)
        print(f"[YOLO] Skipping unsupported weights {weights.name} (not YOLO26/YOLOE)")
        return False

    def _load(self) -> None:
        try:
            from ultralytics.utils import SETTINGS

            SETTINGS.update({"offline": True})
        except Exception:  # noqa: BLE001
            pass
        found = [p for p in self._weight_candidates() if p.exists() and p.stat().st_size > 1024]
        if not found:
            msg = (
                "[YOLO] нет тактических весов yolo26*-ft/n в assets/models — "
                "режим offline (пустые детекции). Проверьте комплект пака."
            )
            print(msg)
            self.model = None
            self.mode = "offline"
            self.kind = "none"
            self._init_error_ru = "Нет тактических весов YOLO26 в assets/models"
            return
        errors: list[str] = []
        for weights in found:
            try:
                if not self._try_load(weights):
                    continue
                self.model_name = weights.name
                self.model_path = weights
                self.mode = "ready"
                self._init_error_ru = ""
                sample = list(self._names.items())[:8]
                print(f"[YOLO] Model loaded successfully: {weights}")
                print(f"[YOLO] kind={self.kind} nc={len(self._names)} sample={sample}")
                return
            except Exception as exc:  # noqa: BLE001
                err = f"{weights.name}: {exc}"
                errors.append(err)
                print(f"[YOLO] Failed {err} — trying next")
                self.model = None
                self.kind = "none"
                self._names = {}
        print("[YOLO] all candidate weights failed — error mode")
        self.mode = "error"
        self._init_error_ru = "Не удалось загрузить YOLO: " + ("; ".join(errors[:3]) or "unknown")
        print(f"[YOLO] RU: {self._init_error_ru}")

    def _detect_device(self) -> None:
        """CUDA → optional DirectML (experimental) → CPU; tier from CPU brand + cores."""
        import os
        import platform

        self._device = "cpu"
        self._device_backend = "cpu"
        self._ort_providers: list[str] = []
        self._cuda_name = ""
        self._degraded = False
        self._use_directml = False
        self._yolo_label = "CPU"
        self._onnx_path: Path | None = None

        torch_cuda = False
        try:
            import torch

            if torch.cuda.is_available():
                torch_cuda = True
                self._device = "cuda:0"
                self._device_backend = "torch-cuda"
                self._yolo_label = "CUDA"
                try:
                    self._cuda_name = torch.cuda.get_device_name(0)
                except Exception:  # noqa: BLE001
                    self._cuda_name = "cuda"
        except Exception:  # noqa: BLE001
            pass

        dml_ok = False
        try:
            from services.yolo_directml import directml_available, list_ort_providers

            self._ort_providers = list_ort_providers()
            dml_ok = directml_available()
            if self._device == "cpu":
                if "CUDAExecutionProvider" in self._ort_providers:
                    self._device_backend = "ort-cuda-available"
                elif dml_ok:
                    self._device_backend = "ort-dml-available"
                elif "TensorrtExecutionProvider" in self._ort_providers:
                    self._device_backend = "ort-trt-available"
        except Exception:  # noqa: BLE001
            self._ort_providers = []

        requested = "auto"
        try:
            from services.db import get_setting

            requested = (get_setting("yolo_inference_backend") or "auto").strip().lower()
        except Exception:  # noqa: BLE001
            requested = (os.environ.get("MURAVEI_YOLO_BACKEND") or "auto").strip().lower()

        try:
            from services.yolo_directml import select_inference_backend

            chosen = select_inference_backend(
                requested, torch_cuda=torch_cuda, dml_ok=dml_ok
            )
        except Exception:  # noqa: BLE001
            chosen = "torch-cuda" if torch_cuda else "cpu"

        if chosen == "directml":
            self._use_directml = True
            self._device = "directml"
            self._device_backend = "directml"
            self._yolo_label = "DirectML"
        elif chosen == "torch-cuda":
            self._use_directml = False
            self._yolo_label = "CUDA"
        else:
            self._use_directml = False
            if not torch_cuda:
                self._device = "cpu"
                self._device_backend = "cpu"
                self._yolo_label = "CPU"

        # Tier: brand hints (i3/i5/i7/i9) + core count
        brand = ""
        try:
            brand = (platform.processor() or "").lower()
        except Exception:  # noqa: BLE001
            brand = ""
        try:
            import psutil

            if not brand:
                brand = (psutil.cpu_freq() and "") or ""
            brand = (brand or platform.uname().processor or "").lower()
        except Exception:  # noqa: BLE001
            pass

        cpus = os.cpu_count() or 4
        if "i3" in brand or cpus <= 4:
            self._tier = "low"
        elif "i9" in brand or "ryzen 9" in brand or cpus >= 16:
            self._tier = "high"
        elif "i7" in brand or "i5" in brand or "ryzen 7" in brand or cpus >= 8:
            self._tier = "mid"
        elif cpus <= 6:
            self._tier = "low"
        elif cpus <= 11:
            self._tier = "mid"
        else:
            self._tier = "high"

        # Adaptive imgsz by tier
        self._imgsz = {"low": 640, "mid": 800, "high": 1024}.get(self._tier, IMGSZ)
        print(
            f"[YOLO] device={self._device} backend={self._device_backend} "
            f"label={self._yolo_label} tier={self._tier} imgsz={self._imgsz} "
            f"cuda={self._cuda_name or '—'} requested={requested} "
            f"ort={self._ort_providers[:3]}"
        )

    def status_snapshot(self) -> dict[str, Any]:
        qsize = self._queue.qsize() if self._queue is not None else 0
        label = getattr(self, "_yolo_label", "CPU")
        eng = self.engine_status()
        return {
            "mode": self.mode,
            "model": self.model_name,
            "kind": self.kind,
            "last_kind": self._last_used_kind,
            "engine_status": eng,
            "nc": len(self._names),
            "device": self._device,
            "device_backend": getattr(self, "_device_backend", "cpu"),
            "yolo_label": label,
            "yolo_badge": f"YOLO: {label}",
            "cuda_name": getattr(self, "_cuda_name", ""),
            "ort_providers": getattr(self, "_ort_providers", []),
            "degraded": getattr(self, "_degraded", False),
            "use_directml": bool(getattr(self, "_use_directml", False)),
            "tier": self._tier,
            "imgsz": getattr(self, "_imgsz", IMGSZ),
            "last_inference_ms": self._last_inference_ms,
            "last_n": self._last_n,
            "nms_mode": self._last_nms_mode,
            "queue_size": qsize,
            "init_error_ru": getattr(self, "_init_error_ru", "") or "",
        }

    def _empty(self, frame_idx: int, time_sec: float, dropped: bool = False) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "frameIdx": frame_idx,
            "timeSec": time_sec,
            "objects": [],
            "ts": time.time(),
            "kind": self.kind,
            "n": 0,
            "ms": 0,
            "nms_mode": "native",
            "model": self.model_name,
            "dropped": dropped,
        }
    def _nms(self, objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ordered = sorted(objects, key=lambda o: float(o.get("confidence") or 0), reverse=True)
        kept: list[dict[str, Any]] = []
        for obj in ordered:
            if any(_box_iou(obj["bbox"], other["bbox"]) >= NMS_IOU for other in kept):
                continue
            kept.append(obj)
        return kept

    def _min_conf_for(self, name: str, floor: float) -> float:
        override = confidence_threshold_for(name)
        if override is not None:
            return override
        blob = (name or "").lower().replace("_", " ")
        if any(tok in blob for tok in _STRICT_TOKENS):
            return max(floor, _STRICT_CONF)
        if "drone" in blob or "uav" in blob or "fpv" in blob:
            return max(floor, _DRONE_CONF)
        if any(tok in blob for tok in _LBS_SOFT_TOKENS):
            return min(floor, _LBS_SOFT_CONF) if floor > 0 else _LBS_SOFT_CONF
        return floor

    def _boxes_to_objects(self, result: Any, orig_w: int, orig_h: int, floor: float) -> list[dict[str, Any]]:
        boxes = getattr(result, "boxes", None)
        if boxes is None or len(boxes) == 0:
            return []
        result_names = getattr(result, "names", None)
        objects: list[dict[str, Any]] = []
        for box in boxes:
            cls_id = int(box.cls[0].item()) if box.cls is not None else 0
            conf = float(box.conf[0].item()) if box.conf is not None else 0.0
            xyxy = box.xyxy[0].tolist()
            x1, y1, x2, y2 = [float(v) for v in xyxy]
            raw_name = self._label(cls_id, result_names)
            name = to_snake_case(canonical_label(raw_name.replace("_", " ")))
            raw_lower = raw_name.lower().replace("_", " ")
            if is_scene_class(name) or is_scene_class(raw_name):
                continue
            if conf < self._min_conf_for(name, floor):
                continue
            bbox = {
                "x1": max(0.0, min(1.0, x1 / orig_w if orig_w else 0.0)),
                "y1": max(0.0, min(1.0, y1 / orig_h if orig_h else 0.0)),
                "x2": max(0.0, min(1.0, x2 / orig_w if orig_w else 0.0)),
                "y2": max(0.0, min(1.0, y2 / orig_h if orig_h else 0.0)),
            }
            area = _box_area(bbox)
            if area >= MAX_SCENE_AREA or area <= 0:
                continue
            # COCO person on large boxes (tank hull, vehicle) → false soldier
            if name == "soldier" and raw_lower in ("person", "human", "pedestrian") and area > 0.05:
                continue
            track_id = None
            box_id = getattr(box, "id", None)
            if box_id is not None:
                try:
                    track_id = int(box_id[0].item() if hasattr(box_id[0], "item") else box_id[0])
                except Exception:  # noqa: BLE001
                    track_id = None
            yaml_id = class_id_for_name(name)
            if yaml_id < 0:
                # Unmapped COCO / unknown — never show to operator
                continue
            objects.append(
                {
                    "id": f"trk-{track_id}" if track_id is not None else str(uuid.uuid4()),
                    "class_id": yaml_id,
                    "class_en": name,
                    "class_ru": name,
                    "confidence": conf,
                    "bbox": bbox,
                    "color": _BOX_COLORS[max(cls_id, 0) % len(_BOX_COLORS)],
                    "origin": "auto",
                    "track_id": track_id,
                }
            )
        return objects

    def _run_model(self, model: Any, img: Any, confidence: float, *, use_track: bool = False) -> list[dict[str, Any]]:
        orig_w, orig_h = img.size
        floor = float(confidence) if confidence else DEFAULT_CONF
        # Pull boxes a bit softer than UI floor so LBS cues (trench/path/wire) survive;
        # per-class floors are applied in _boxes_to_objects.
        configured_min = minimum_confidence_threshold()
        predict_conf = min(
            floor,
            _LBS_SOFT_CONF,
            configured_min if configured_min is not None else floor,
        )
        imgsz = int(getattr(self, "_imgsz", IMGSZ) or IMGSZ)

        # Experimental DirectML path (optional) — any error → CPU torch, logged warning.
        if getattr(self, "_use_directml", False):
            try:
                from services.yolo_directml import ensure_onnx_export, run_directml_onnx

                weights = Path(getattr(self, "model_path", None) or "")
                if not weights.is_file():
                    # Resolve from loaded model name
                    candidate = WEIGHTS_DIR / (self.model_name or "")
                    if candidate.is_file():
                        weights = candidate
                    else:
                        ft = BASE_DIR / "assets" / "models" / (self.model_name or "")
                        weights = ft if ft.is_file() else weights
                onnx_path = ensure_onnx_export(weights, imgsz=min(imgsz, 640))
                self._onnx_path = onnx_path
                raw = run_directml_onnx(
                    onnx_path, img, conf=predict_conf, imgsz=min(imgsz, 640)
                )
                objects: list[dict[str, Any]] = []
                for row in raw:
                    cls_id = int(row.get("cls_id") or 0)
                    name = self._names.get(cls_id) or str(cls_id)
                    name = canonical_label(name) or name
                    yaml_id = class_id_for_name(name)
                    if yaml_id < 0:
                        continue
                    conf = float(row.get("confidence") or 0)
                    bbox = row.get("bbox") or {}
                    objects.append(
                        {
                            "id": str(uuid.uuid4()),
                            "class_id": yaml_id,
                            "class_en": name,
                            "class_ru": name,
                            "confidence": conf,
                            "bbox": bbox,
                            "color": _BOX_COLORS[max(cls_id, 0) % len(_BOX_COLORS)],
                            "origin": "auto",
                            "track_id": None,
                        }
                    )
                return [
                    o
                    for o in objects
                    if _keep_live_label(o["class_en"]) and not _is_osd_box(o["bbox"])
                ]
            except Exception as exc:  # noqa: BLE001
                print(f"[YOLO] DirectML fail → CPU fallback (не молча): {exc}")
                print("[YOLO] Перезапустите для ускорения (DirectML/ORT).")
                try:
                    from services.runtime_log import write as runtime_write

                    runtime_write(
                        "warn",
                        "yolo",
                        f"DirectML fallback to CPU: {exc}",
                    )
                except Exception:  # noqa: BLE001
                    pass
                self._use_directml = False
                self._device = "cpu"
                self._device_backend = "cpu-fallback-directml"
                self._yolo_label = "CPU"
                self._degraded = True

        kwargs: dict[str, Any] = {
            "source": img,
            "imgsz": imgsz,
            "conf": predict_conf,
            "iou": NMS_IOU,
            "agnostic_nms": False,
            "verbose": False,
            "device": self._device if str(self._device).startswith("cuda") else "cpu",
        }
        try:
            # ByteTrack needs `lap`; Ultralytics tries to pip-install it (breaks air-gap).
            results = model.predict(**kwargs)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if str(self._device).startswith("cuda") and (
                "out of memory" in msg or "cuda" in msg and "memory" in msg
            ):
                print(f"[YOLO] CUDA OOM/fail → CPU fallback: {exc}")
                self._device = "cpu"
                self._device_backend = "cpu-fallback-oom"
                self._yolo_label = "CPU"
                self._degraded = True
                kwargs["device"] = "cpu"
                results = model.predict(**kwargs)
            else:
                raise
        if not results:
            return []
        return [o for o in self._boxes_to_objects(results[0], orig_w, orig_h, floor) if _keep_live_label(o["class_en"]) and not _is_osd_box(o["bbox"])]

    def _predict_tiles(self, model: Any, img: Any, confidence: float) -> list[dict[str, Any]]:
        w, h = img.size
        if w < 80 or h < 80:
            return []
        tile_w = max(64, int(w / (2 - TILE_OVERLAP)))
        tile_h = max(64, int(h / (2 - TILE_OVERLAP)))
        step_x = max(32, int(tile_w * (1 - TILE_OVERLAP)))
        step_y = max(32, int(tile_h * (1 - TILE_OVERLAP)))
        objects: list[dict[str, Any]] = []
        y0 = 0
        while y0 < h:
            x0 = 0
            y1 = min(h, y0 + tile_h)
            y0c = max(0, y1 - tile_h)
            while x0 < w:
                x1 = min(w, x0 + tile_w)
                x0c = max(0, x1 - tile_w)
                crop = img.crop((x0c, y0c, x1, y1))
                tw, th = max(1, x1 - x0c), max(1, y1 - y0c)
                for obj in self._run_model(model, crop, confidence):
                    bbox = obj["bbox"]
                    obj["bbox"] = {
                        "x1": max(0.0, min(1.0, (bbox["x1"] * tw + x0c) / w)),
                        "y1": max(0.0, min(1.0, (bbox["y1"] * th + y0c) / h)),
                        "x2": max(0.0, min(1.0, (bbox["x2"] * tw + x0c) / w)),
                        "y2": max(0.0, min(1.0, (bbox["y2"] * th + y0c) / h)),
                    }
                    objects.append(obj)
                if x1 >= w:
                    break
                x0 += step_x
            if y1 >= h:
                break
            y0 += step_y
        return objects

    def _ensure_fallback(self) -> Any:
        if self._fallback is not None:
            return self._fallback
        path = WEIGHTS_DIR / "yolo26n.pt"
        if not path.exists() or path.stat().st_size < 1024:
            return None
        from ultralytics import YOLO

        self._fallback = YOLO(str(path))
        print(f"[YOLO] Closed-set fallback loaded: {path.name}")
        return self._fallback

    def _viewer_motion(self, viewer_id: str):
        from services.motion import MotionState

        key = viewer_id or "default"
        st = self._motion_states.get(key)
        if st is None:
            st = MotionState()
            self._motion_states[key] = st
        return st

    def _viewer_tracker(self, viewer_id: str):
        from services.tracker import IoUTracker

        key = viewer_id or "default"
        tr = self._trackers.get(key)
        if tr is None:
            tr = IoUTracker()
            self._trackers[key] = tr
        return tr

    def _apply_motion_track(
        self,
        objects: list[dict[str, Any]],
        image_bytes: bytes,
        viewer_id: str,
    ) -> tuple[list[dict[str, Any]], dict[str, float]]:
        """Ego optical flow + IoU tracker → stable ids + motion vectors."""
        ego = {"ego_vx": 0.0, "ego_vy": 0.0}
        if not objects and not image_bytes:
            return objects, ego
        try:
            import numpy as np
            from PIL import Image

            from services.motion import estimate_ego

            rgb = np.asarray(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
            st = self._viewer_motion(viewer_id)
            ego_vx, ego_vy = estimate_ego(st, rgb)
            ego = {"ego_vx": round(ego_vx, 5), "ego_vy": round(ego_vy, 5)}
            tracker = self._viewer_tracker(viewer_id)
            tracked = tracker.update(objects, ego_vx=ego_vx, ego_vy=ego_vy)
            return tracked, ego
        except Exception as exc:  # noqa: BLE001
            print(f"[YOLO] motion/track skip: {exc}")
            return objects, ego

    def _predict_sync(
        self,
        image_bytes: bytes,
        confidence: float,
        frame_idx: int,
        time_sec: float,
        viewer_id: str = "default",
    ) -> dict[str, Any]:
        if self.model is None or self.mode != "ready":
            return self._empty(frame_idx, time_sec)
        if not image_bytes:
            return self._empty(frame_idx, time_sec)
        try:
            from PIL import Image

            t0 = time.time()
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            floor = float(confidence) if confidence else DEFAULT_CONF
            used = self.kind
            nms_mode = "native"

            # Sprint 1: primary first (YOLO26-ft / YOLOE) — native predict, no aggressive _nms
            objects = self._run_model(self.model, img, floor, use_track=False)
            objects = _drop_outer_boxes(objects)
            objects = [o for o in objects if not _is_osd_box(o["bbox"])]

            # COCO fallback only if primary returned nothing
            if not objects:
                primary_is_coco_nano = self.model_name.lower() == "yolo26n.pt"
                fallback = None if primary_is_coco_nano else self._ensure_fallback()
                if fallback is not None:
                    objects = self._run_model(fallback, img, COCO_FALLBACK_CONF, use_track=False)
                    if len(objects) < 2:
                        tiled = self._predict_tiles(fallback, img, COCO_FALLBACK_CONF)
                        if tiled:
                            objects = self._nms(objects + tiled)
                            nms_mode = "post"
                    if objects:
                        objects = _drop_outer_boxes(self._nms(objects))
                        objects = [o for o in objects if not _is_osd_box(o["bbox"])]
                        used = "yolo26-closed"
                        nms_mode = "post"

            # Sprint 3: ego-motion + IoU tracks
            return self._finalize_sync(
                objects, image_bytes, frame_idx, time_sec, viewer_id,
                used, nms_mode, t0, img.size,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[YOLO] predict error: {exc}")
            return {
                "mode": "error",
                "frameIdx": frame_idx,
                "timeSec": time_sec,
                "objects": [],
                "ts": time.time(),
                "error": str(exc),
                "kind": self.kind,
                "n": 0,
                "ms": 0,
                "nms_mode": "native",
                "model": self.model_name,
            }

    def _finalize_sync(
        self,
        objects: list[dict[str, Any]],
        image_bytes: bytes,
        frame_idx: int,
        time_sec: float,
        viewer_id: str,
        used: str,
        nms_mode: str,
        t0: float,
        img_size: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        """Shared tail of _predict_sync / _predict_sync_sahi: track + envelope."""
        raw_n = len(objects)
        objects, ego = self._apply_motion_track(objects, image_bytes, viewer_id)
        # --- Response validator (defense-in-depth) ---
        from services.response_validator import get_validator

        objects = get_validator().validate_batch(objects)
        ms = int((time.time() - t0) * 1000)
        self._last_inference_ms = ms
        self._last_n = len(objects)
        self._last_nms_mode = nms_mode
        self._last_used_kind = used
        sample = [o["class_en"] for o in objects[:6]]
        size_str = f" size={img_size}" if img_size else ""
        print(
            f"[YOLO] infer {used} nms={nms_mode} {ms}ms n={len(objects)} "
            f"ego=({ego.get('ego_vx')},{ego.get('ego_vy')}) {sample}{size_str}"
        )
        return {
            "mode": self.mode,
            "frameIdx": frame_idx,
            "timeSec": time_sec,
            "objects": objects,
            "ts": time.time(),
            "kind": used,
            "n": len(objects),
            "raw_n": raw_n,
            "ms": ms,
            "nms_mode": nms_mode,
            "model": self.model_name,
            "model_nc": len(self._names),
            "device": self._device,
            "ego": ego,
            "viewerId": viewer_id,
        }

    def _predict_sync_sahi(
        self,
        image_bytes: bytes,
        confidence: float,
        frame_idx: int,
        time_sec: float,
        viewer_id: str = "default",
        slice_height: int = 512,
        slice_width: int = 512,
        overlap_ratio: float = 0.2,
    ) -> dict[str, Any]:
        """SAHI slicing path. Reuses the live model; same output contract."""
        if self.model is None or self.mode != "ready":
            return self._empty(frame_idx, time_sec)
        if not image_bytes:
            return self._empty(frame_idx, time_sec)
        try:
            from PIL import Image

            from services.sahi_yolo_engine import slice_and_detect

            t0 = time.time()
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            floor = float(confidence) if confidence else DEFAULT_CONF
            objects = slice_and_detect(
                self, img, floor, slice_height, slice_width, overlap_ratio
            )
            objects = _drop_outer_boxes(self._nms(objects))
            objects = [o for o in objects if not _is_osd_box(o["bbox"])]
            used = self.kind
            nms_mode = "sahi"
            return self._finalize_sync(
                objects, image_bytes, frame_idx, time_sec, viewer_id,
                used, nms_mode, t0, img.size,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[YOLO] sahi predict error: {exc}")
            return {
                "mode": "error",
                "frameIdx": frame_idx,
                "timeSec": time_sec,
                "objects": [],
                "ts": time.time(),
                "error": str(exc),
                "kind": self.kind,
                "n": 0,
                "ms": 0,
                "nms_mode": "sahi",
                "model": self.model_name,
            }

    async def start_worker(self) -> None:
        if self._queue is not None:
            return
        self._queue = asyncio.Queue(maxsize=QUEUE_MAX)
        self._worker_task = asyncio.create_task(self._worker_loop(), name="yolo-infer-worker")
        print("[YOLO] Infer queue worker started (max 1 in-flight, queue=4)")

    async def _worker_loop(self) -> None:
        assert self._queue is not None
        while True:
            job = await self._queue.get()
            try:
                if job.use_sahi:
                    result = await asyncio.to_thread(
                        self._predict_sync_sahi,
                        job.image_bytes,
                        job.confidence,
                        job.frame_idx,
                        job.time_sec,
                        job.viewer_id,
                        job.slice_height,
                        job.slice_width,
                        job.overlap_ratio,
                    )
                else:
                    result = await asyncio.to_thread(
                        self._predict_sync,
                        job.image_bytes,
                        job.confidence,
                        job.frame_idx,
                        job.time_sec,
                        job.viewer_id,
                    )
                if not job.future.done():
                    job.future.set_result(result)
            except Exception as exc:  # noqa: BLE001
                if not job.future.done():
                    job.future.set_exception(exc)
            finally:
                self._queue.task_done()

    async def infer(
        self,
        image_bytes: bytes,
        confidence: float = DEFAULT_CONF,
        frame_idx: int = 0,
        time_sec: float = 0.0,
        viewer_id: str = "default",
    ) -> dict[str, Any]:
        if self.mode != "ready" or self.model is None:
            return self._empty(frame_idx, time_sec)
        await self.start_worker()
        assert self._queue is not None
        loop = asyncio.get_running_loop()
        job = _InferJob(
            image_bytes=image_bytes,
            confidence=confidence,
            frame_idx=frame_idx,
            time_sec=time_sec,
            viewer_id=viewer_id or "default",
            future=loop.create_future(),
        )
        if self._queue.full():
            try:
                dropped = self._queue.get_nowait()
                if not dropped.future.done():
                    dropped.future.set_result(self._empty(dropped.frame_idx, dropped.time_sec, dropped=True))
                self._queue.task_done()
            except asyncio.QueueEmpty:
                pass
        await self._queue.put(job)
        return await job.future

    async def infer_sahi(
        self,
        image_bytes: bytes,
        confidence: float = DEFAULT_CONF,
        frame_idx: int = 0,
        time_sec: float = 0.0,
        viewer_id: str = "default",
        slice_height: int = 512,
        slice_width: int = 512,
        overlap_ratio: float = 0.2,
    ) -> dict[str, Any]:
        """SAHI (sliced) inference path. Same contract as infer() + ``sahi: True``."""
        if self.mode != "ready" or self.model is None:
            return self._empty(frame_idx, time_sec)
        await self.start_worker()
        assert self._queue is not None
        loop = asyncio.get_running_loop()
        job = _InferJob(
            image_bytes=image_bytes,
            confidence=confidence,
            frame_idx=frame_idx,
            time_sec=time_sec,
            viewer_id=viewer_id or "default",
            future=loop.create_future(),
            use_sahi=True,
            slice_height=slice_height,
            slice_width=slice_width,
            overlap_ratio=overlap_ratio,
        )
        if self._queue.full():
            try:
                dropped = self._queue.get_nowait()
                if not dropped.future.done():
                    dropped.future.set_result(self._empty(dropped.frame_idx, dropped.time_sec, dropped=True))
                self._queue.task_done()
            except asyncio.QueueEmpty:
                pass
        await self._queue.put(job)
        result = await job.future
        result["sahi"] = True
        return result

_engine: YoloEngine | None = None


def get_yolo_engine() -> YoloEngine:
    global _engine
    if _engine is None:
        _engine = YoloEngine()
    return _engine
