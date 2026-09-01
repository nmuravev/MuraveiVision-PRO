"""Quick-finetune YOLO from operator crops — SSE progress."""
from __future__ import annotations

import json
import shutil
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from main import BASE_DIR
from services.db import CROPS_DIR, list_detections, normalize_media_path
from services.yolo_engine import WEIGHTS_DIR

TRAIN_ROOT = BASE_DIR / "cache" / "train_run"
DATASET_DIR = TRAIN_ROOT / "dataset"
LOG_PATH = BASE_DIR / "logs" / "train.log"

_lock = threading.Lock()
_state: dict[str, Any] = {
    "status": "idle",  # idle|running|error|done
    "message": "",
    "epoch": 0,
    "epochs": 0,
    "box_loss": None,
    "cls_loss": None,
    "map50": None,
    "map50_95": None,
    "batch": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
}
_events: list[dict[str, Any]] = []
_stop = threading.Event()
_thread: threading.Thread | None = None


def _log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line)
    print(f"[TRAIN] {msg}")


def _emit(event: dict[str, Any]) -> None:
    payload = {"ts": time.time(), **event}
    with _lock:
        _events.append(payload)
        if len(_events) > 500:
            del _events[:200]
        for k, v in event.items():
            if k in _state:
                _state[k] = v
        if "status" in event:
            _state["status"] = event["status"]
        if "message" in event:
            _state["message"] = event["message"]
        if "error" in event:
            _state["error"] = event["error"]


def status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def drain_events(after_idx: int = 0) -> tuple[list[dict[str, Any]], int]:
    with _lock:
        chunk = _events[after_idx:]
        return chunk, len(_events)


def _is_detect_base(path: Path) -> bool:
    """Quick-train uses box labels only — never YOLOE / *-seg* checkpoints."""
    name = path.name.lower()
    if not name.endswith(".pt"):
        return False
    if "seg" in name or "yoloe" in name:
        return False
    return path.is_file() and path.stat().st_size > 1024


def _active_weights() -> Path:
    """
    Hard detect-only base for crop finetune.
    Never use live YOLOE / *-seg* — Ultralytics would demand polygon labels.
    """
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    # Order matches field plan: nano first, then small. No ft/seg/yoloe as base.
    preferred = [
        WEIGHTS_DIR / "yolo26n.pt",
        BASE_DIR / "assets" / "models" / "yolo26n.pt",
        WEIGHTS_DIR / "yolo26n-ft.pt",
        BASE_DIR / "assets" / "models" / "yolo26n-ft.pt",
        WEIGHTS_DIR / "yolo26s.pt",
        BASE_DIR / "assets" / "models" / "yolo26s.pt",
    ]
    for p in preferred:
        if _is_detect_base(p):
            _log(f"Инициализация обучения. Base model: {p.name}")
            return p
    raise FileNotFoundError(
        "Нужен yolo26n.pt (или yolo26s.pt) в runs/detect/train/weights/ "
        "или assets/models/. YOLOE *-seg* для быстрого обучения не используется."
    )


def _resolve_train_device() -> str | int:
    """Prefer CUDA for Ultralytics train(); fall back to CPU."""
    try:
        import torch

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            _log(f"CUDA train device: {name}")
            return 0
    except Exception as exc:  # noqa: BLE001
        _log(f"CUDA probe failed: {exc}")
    _log("Training on CPU (no CUDA torch)")
    return "cpu"


def _train_batches(device: str | int) -> tuple[int, ...]:
    return (16, 8, 4, 2) if device != "cpu" else (8, 4, 2)


def _build_dataset(source_video: str | None = None) -> tuple[Path, int]:
    detections = [d for d in list_detections(include_deleted=False) if not d.get("is_deleted")]
    if source_video:
        key = normalize_media_path(source_video)
        detections = [
            d for d in detections if normalize_media_path(str(d.get("source_video") or "")) == key
        ]
    if len(detections) < 3:
        raise RuntimeError(
            "Need at least 3 saved detections (crops) to train"
            + (f" for source={source_video}" if source_video else "")
        )

    if DATASET_DIR.exists():
        shutil.rmtree(DATASET_DIR, ignore_errors=True)
    img_dir = DATASET_DIR / "images"
    lbl_dir = DATASET_DIR / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    names: list[str] = list(
        OrderedDict((str(d["class_name"]), None) for d in detections).keys()
    )
    name_to_idx = {n: i for i, n in enumerate(names)}
    written = 0
    for row in detections:
        crop = Path(str(row["crop_path"])) if row.get("crop_path") else CROPS_DIR / f"{row['id']}.jpg"
        if not crop.is_file():
            crop = CROPS_DIR / f"{row['id']}.jpg"
        if not crop.is_file():
            continue
        dest = img_dir / f"{row['id']}.jpg"
        shutil.copy2(crop, dest)
        # Crops are object crops — label as nearly full-frame instance (detect format)
        line = f"{name_to_idx[str(row['class_name'])]} 0.5 0.5 0.95 0.95\n"
        (lbl_dir / f"{row['id']}.txt").write_text(line, encoding="utf-8")
        written += 1

    if written < 3:
        raise RuntimeError(f"Only {written} crops on disk — need ≥3")

    yaml_path = DATASET_DIR / "dataset.yaml"
    lines = [
        f"path: {DATASET_DIR.as_posix()}",
        "train: images",
        "val: images",
        "task: detect",
        "names:",
    ]
    for i, n in enumerate(names):
        lines.append(f"  {i}: {n}")
    yaml_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return yaml_path, written


def _atomic_promote(new_best: Path) -> Path:
    """Save finetune as assets/models/yolo26n-ft.pt (+ mirror under WEIGHTS_DIR)."""
    assets = BASE_DIR / "assets" / "models"
    assets.mkdir(parents=True, exist_ok=True)
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)

    target = assets / "yolo26n-ft.pt"
    mirror = WEIGHTS_DIR / "yolo26n-ft.pt"

    for dest in (target, mirror):
        if dest.is_file():
            # Unified backup suffix: model.pt.backup
            backup = Path(f"{dest}.backup")
            if backup.exists():
                backup.unlink()
            shutil.copy2(dest, backup)
            _log(f"backup → {backup}")
        shutil.copy2(new_best, dest)

    _log(f"Успех! Модель сохранена в: {target}")
    return target


def _run(epochs: int = 10, source_video: str | None = None) -> None:
    global _thread
    try:
        _emit({"status": "running", "message": "Preparing dataset…", "error": None})
        yaml_path, n = _build_dataset(source_video=source_video)
        base = _active_weights()
        src_note = f" source={Path(source_video).name}" if source_video else ""
        _emit(
            {
                "message": f"Dataset ready ({n} images){src_note}. Base model: {base.name}",
                "epochs": epochs,
            }
        )

        from ultralytics import YOLO

        print(f"[TRAIN] Инициализация обучения. Base model: {base.name}")
        model = YOLO(str(base))
        device = _resolve_train_device()
        batches = list(_train_batches(device))
        last_err: Exception | None = None
        run_dir = TRAIN_ROOT / "ultralytics"
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)

        class _Cb:
            def on_train_epoch_end(self, trainer):  # noqa: N802
                if _stop.is_set():
                    trainer.stop = True
                metrics = getattr(trainer, "metrics", {}) or {}
                loss = getattr(trainer, "loss_items", None)
                box_loss = cls_loss = None
                try:
                    if loss is not None and len(loss) >= 2:
                        box_loss = float(loss[0])
                        cls_loss = float(loss[1])
                except Exception:
                    pass
                epoch = int(getattr(trainer, "epoch", 0)) + 1
                _emit(
                    {
                        "status": "running",
                        "epoch": epoch,
                        "epochs": int(getattr(trainer, "epochs", epochs)),
                        "box_loss": box_loss,
                        "cls_loss": cls_loss,
                        "map50": float(metrics.get("metrics/mAP50(B)", metrics.get("mAP50", 0)) or 0)
                        if metrics
                        else None,
                        "map50_95": float(
                            metrics.get("metrics/mAP50-95(B)", metrics.get("mAP50-95", 0)) or 0
                        )
                        if metrics
                        else None,
                        "message": f"Epoch {epoch}/{epochs}",
                    }
                )

        # Register once per training session — do not re-add on OOM batch retry.
        model.add_callback("on_train_epoch_end", _Cb().on_train_epoch_end)

        for batch in batches:
            if _stop.is_set():
                _emit({"status": "idle", "message": "Stopped by user"})
                return
            try:
                _emit({"message": f"Training batch={batch} device={device} (detect)", "batch": batch})
                model.train(
                    data=str(yaml_path),
                    task="detect",
                    imgsz=1024,
                    batch=batch,
                    epochs=epochs,
                    device=device,
                    # Sprint 3: detect-only YOLO26 — MuSGD-style SGD + ProgLoss schedule
                    optimizer="SGD",
                    momentum=0.937,
                    lr0=0.001,
                    lrf=0.01,
                    weight_decay=0.0005,
                    box=7.5,
                    cls=0.5,
                    dfl=1.5,
                    warmup_epochs=1.0,
                    close_mosaic=max(1, int(epochs * 0.2)),
                    # STAL-ish small-target emphasis via heavy copy-paste / light mosaic
                    copy_paste=1.0,
                    mosaic=0.5,
                    mixup=0.0,
                    project=str(TRAIN_ROOT),
                    name="ultralytics",
                    exist_ok=True,
                    verbose=False,
                    plots=False,
                    save=True,
                )
                last_err = None
                break
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                msg = str(exc).lower()
                _log(f"batch={batch} failed: {exc}")
                if "segment dataset" in msg or "len(segments)" in msg:
                    raise RuntimeError(
                        "Detect/segment mismatch — refusing seg weights for box crops. "
                        f"Base was {base.name}. Need yolo26n.pt."
                    ) from exc
                if "out of memory" in msg or ("cuda" in msg and "memory" in msg):
                    _emit({"message": f"OOM at batch={batch}, retrying smaller…"})
                    try:
                        import torch

                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    except Exception:  # noqa: BLE001
                        pass
                    continue
                raise

        if last_err is not None:
            raise last_err

        candidates = [
            TRAIN_ROOT / "ultralytics" / "weights" / "best.pt",
            TRAIN_ROOT / "ultralytics" / "weights" / "last.pt",
        ]
        new_best = next((p for p in candidates if p.is_file()), None)
        if new_best is None:
            raise RuntimeError("Training finished but best.pt not found")
        promoted = _atomic_promote(new_best)
        _emit(
            {
                "status": "done",
                "message": f"Done. Model → {promoted}",
                "finished_at": time.time(),
            }
        )
        try:
            from services.yolo_engine import get_yolo_engine

            eng = get_yolo_engine()
            if eng.force_load(promoted):
                _log(f"YOLO engine force-loaded {promoted.name}")
            else:
                _log("reload: force_load returned False")
        except Exception as exc:  # noqa: BLE001
            _log(f"reload skipped: {exc}")
    except Exception as exc:  # noqa: BLE001
        _log(f"ERROR {exc}")
        _emit({"status": "error", "error": str(exc), "message": str(exc), "finished_at": time.time()})
    finally:
        with _lock:
            _thread = None

def start(epochs: int = 10, source_video: str | None = None) -> dict[str, Any]:
    global _thread
    with _lock:
        if _state["status"] == "running" or (_thread and _thread.is_alive()):
            raise RuntimeError("Training already running")
        _stop.clear()
        _events.clear()
        _state.update(
            {
                "status": "running",
                "message": "Starting…",
                "epoch": 0,
                "epochs": epochs,
                "box_loss": None,
                "cls_loss": None,
                "map50": None,
                "map50_95": None,
                "batch": None,
                "started_at": time.time(),
                "finished_at": None,
                "error": None,
            }
        )
        _thread = threading.Thread(
            target=_run,
            args=(epochs, source_video),
            daemon=True,
            name="yolo-train",
        )
        _thread.start()
    return status()


def stop() -> dict[str, Any]:
    _stop.set()
    _emit({"message": "Stop requested…"})
    return status()
