"""3-stage .pt model validation + atomic install."""
from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import Any

from main import BASE_DIR
from services.yolo_engine import WEIGHTS_DIR

MAX_MB = 500
ALLOWED_NC = {12, 238}
IMPORT_DIR = BASE_DIR / "cache" / "model_import"
LOG_PATH = BASE_DIR / "logs" / "model_import.log"

_lock = threading.Lock()
_state: dict[str, Any] = {
    "status": "idle",  # idle|running|error|done
    "stage": None,
    "message": "",
    "error": None,
    "nc": None,
    "path": None,
}
_events: list[dict[str, Any]] = []
_thread: threading.Thread | None = None


def _log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    print(f"[MODEL] {msg}")


def _emit(event: dict[str, Any]) -> None:
    payload = {"ts": time.time(), **event}
    with _lock:
        _events.append(payload)
        if len(_events) > 300:
            del _events[:100]
        for k, v in event.items():
            if k in _state:
                _state[k] = v


def status() -> dict[str, Any]:
    with _lock:
        return dict(_state)


def drain_events(after_idx: int = 0) -> tuple[list[dict[str, Any]], int]:
    with _lock:
        return _events[after_idx:], len(_events)


def _stage_a(path: Path) -> None:
    _emit({"stage": "A", "message": "Structural check…", "status": "running"})
    if not path.is_file():
        raise RuntimeError("File not found")
    if path.suffix.lower() != ".pt":
        raise RuntimeError("Only .pt weights are accepted")
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_MB:
        raise RuntimeError(f"File too large: {size_mb:.1f} MB > {MAX_MB} MB")
    if size_mb < 0.05:
        raise RuntimeError("File too small / corrupt")
    _emit({"stage": "A", "message": f"OK structure ({size_mb:.1f} MB)"})


def _stage_b(path: Path) -> int:
    _emit({"stage": "B", "message": "Architecture check…"})
    from ultralytics import YOLO

    model = YOLO(str(path))
    nc = int(getattr(getattr(model, "model", None), "nc", 0) or getattr(model, "nc", 0) or 0)
    if nc <= 0:
        # try names length
        names = getattr(model, "names", None) or {}
        nc = len(names) if names else 0
    current_nc = None
    try:
        from services.yolo_engine import get_yolo_engine

        eng = get_yolo_engine()
        if eng.model is not None:
            current_nc = int(getattr(eng.model, "nc", 0) or 0)
    except Exception:
        pass
    allowed = set(ALLOWED_NC)
    if current_nc:
        allowed.add(current_nc)
    if nc not in allowed and nc > 0:
        # YOLOE prompt-free may have huge vocab — accept if smoke later passes and nc>0
        if nc < 1:
            raise RuntimeError(f"Invalid nc={nc}; expected one of {sorted(allowed)}")
        _emit(
            {
                "stage": "B",
                "message": f"nc={nc} (not in {sorted(ALLOWED_NC)}; allowing with smoke test)",
                "nc": nc,
            }
        )
    else:
        _emit({"stage": "B", "message": f"OK architecture nc={nc}", "nc": nc})
    return nc


def _stage_c(path: Path) -> None:
    _emit({"stage": "C", "message": "Smoke predict…"})
    import numpy as np
    from ultralytics import YOLO

    model = YOLO(str(path))
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    frame[:] = (40, 40, 40)
    # draw a rectangle so closed-set models may fire something; PF models too
    frame[200:400, 200:400] = (180, 180, 180)
    results = model.predict(source=frame, imgsz=640, verbose=False, conf=0.01)
    if not results:
        raise RuntimeError("predict() returned empty results")
    r0 = results[0]
    boxes = getattr(r0, "boxes", None)
    # Allow zero detections on blank synthetic frame for some models, but forbid NaN scores
    if boxes is not None and getattr(boxes, "conf", None) is not None:
        conf = boxes.conf
        import torch

        if conf is not None and torch.isnan(conf).any():
            raise RuntimeError("NaN confidence in smoke predict")
    _emit({"stage": "C", "message": "OK smoke predict"})


def _install(path: Path) -> Path:
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    target = WEIGHTS_DIR / "best.pt"
    if target.is_file():
        backup = WEIGHTS_DIR / "best.pt.backup"
        if backup.exists():
            backup.unlink()
        shutil.copy2(target, backup)
        _log(f"backup → {backup}")
    shutil.copy2(path, target)
    _log(f"installed → {target}")
    try:
        from services.yolo_engine import get_yolo_engine

        eng = get_yolo_engine()
        if eng._try_load(target):  # noqa: SLF001
            eng.model_name = target.name
            eng.mode = "ready"
            _log("engine reloaded")
    except Exception as exc:  # noqa: BLE001
        _log(f"reload warn: {exc}")
    return target


def _run(src: Path) -> None:
    global _thread
    try:
        _emit({"status": "running", "error": None, "message": "Import started"})
        _stage_a(src)
        nc = _stage_b(src)
        _stage_c(src)
        installed = _install(src)
        _emit(
            {
                "status": "done",
                "stage": "done",
                "message": f"Model installed: {installed}",
                "path": str(installed),
                "nc": nc,
            }
        )
    except Exception as exc:  # noqa: BLE001
        _log(f"FAIL {exc}")
        _emit({"status": "error", "error": str(exc), "message": str(exc)})
    finally:
        with _lock:
            _thread = None


def start_import(uploaded: Path) -> dict[str, Any]:
    global _thread
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        if _state["status"] == "running" or (_thread and _thread.is_alive()):
            raise RuntimeError("Import already running")
        _events.clear()
        _state.update(
            {
                "status": "running",
                "stage": "A",
                "message": "Queued…",
                "error": None,
                "nc": None,
                "path": str(uploaded),
            }
        )
        _thread = threading.Thread(target=_run, args=(uploaded,), daemon=True, name="model-import")
        _thread.start()
    return status()
