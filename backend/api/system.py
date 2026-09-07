"""System telemetry, self-test, failure simulation (engineer+)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from main import BASE_DIR
from services.hardware import hardware_spec
from services.security import require_role
from services.db import get_setting, set_setting

router = APIRouter(prefix="/api/system", tags=["system"])

_sim: dict[str, Any] = {"active": None}


@router.get("/hardware")
async def hardware(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, Any]:
    from services.accelerator import log_profile_once, profile_snapshot

    log_profile_once()
    spec = hardware_spec()
    # enrich with optional pynvml
    try:
        import pynvml

        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
        name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(name, bytes):
            name = name.decode("utf-8", errors="replace")
        spec["gpu_name"] = str(name)
        spec["vram_total_mb"] = int(mem.total / (1024 * 1024))
        spec["vram_used_mb"] = int(mem.used / (1024 * 1024))
        spec["vram_free_mb"] = int(mem.free / (1024 * 1024))
        spec["gpu_temp_c"] = int(temp)
        pynvml.nvmlShutdown()
    except Exception as exc:  # noqa: BLE001
        spec["pynvml"] = str(exc)

    # torch.cuda fallback when NVML missing / incomplete
    if "vram_total_mb" not in spec or not spec.get("vram_total_mb"):
        try:
            import torch

            if torch.cuda.is_available():
                free_b, total_b = torch.cuda.mem_get_info()
                used_b = int(total_b) - int(free_b)
                spec["gpu_name"] = spec.get("gpu_name") or torch.cuda.get_device_name(0)
                spec["vram_total_mb"] = int(total_b / (1024 * 1024))
                spec["vram_used_mb"] = int(used_b / (1024 * 1024))
                spec["vram_free_mb"] = int(free_b / (1024 * 1024))
            else:
                spec.setdefault("gpu_name", "CPU")
                spec.setdefault("vram_total_mb", 0)
                spec.setdefault("vram_used_mb", 0)
                spec.setdefault("vram_free_mb", 0)
        except Exception as exc:  # noqa: BLE001
            spec["torch_cuda"] = str(exc)
            spec.setdefault("gpu_name", "Unknown")
            spec.setdefault("vram_total_mb", 0)
            spec.setdefault("vram_used_mb", 0)
            spec.setdefault("vram_free_mb", 0)

    total_mb = int(spec.get("vram_total_mb") or 0)
    used_mb = int(spec.get("vram_used_mb") or 0)
    free_mb = spec.get("vram_free_mb")
    if free_mb is None:
        free_mb = max(0, total_mb - used_mb)
        spec["vram_free_mb"] = int(free_mb)
    else:
        free_mb = int(free_mb)

    spec["vram_total_gb"] = round(total_mb / 1024, 2)
    spec["vram_used_gb"] = round(used_mb / 1024, 2)
    spec["vram_free_gb"] = round(free_mb / 1024, 2)
    spec.setdefault("gpu_name", "CPU" if total_mb <= 0 else spec.get("gpu") or "GPU")

    snap = profile_snapshot()
    spec.update(snap)
    try:
        from services.yolo_directml import directml_available

        spec["directml_available"] = directml_available()
    except Exception:  # noqa: BLE001
        spec["directml_available"] = False

    try:
        from services.hardware_detect import detect_all

        hw = detect_all()
        spec["portable_tier"] = (hw.get("tier") or {}).get("tier")
        spec["portable_tier_label_ru"] = (hw.get("tier") or {}).get("label_ru")
        spec["build_profile"] = hw.get("build_profile")
        spec["system_badge_ru"] = hw.get("badge_ru")
        spec["portable_mismatch"] = hw.get("mismatch")
        spec["components"] = {
            "colmap": hw.get("colmap"),
            "alicevision": hw.get("alicevision"),
            "ffmpeg": hw.get("ffmpeg"),
            "python": hw.get("python"),
            "gpu": hw.get("gpu"),
        }
    except Exception as exc:  # noqa: BLE001
        spec["hardware_detect_error"] = str(exc)

    if _sim["active"] == "gpu_oom":
        spec["simulated"] = "gpu_oom"
        spec["vram_used_mb"] = spec.get("vram_total_mb", 8192)
        spec["vram_free_mb"] = 0
        spec["vram_used_gb"] = round(int(spec["vram_used_mb"]) / 1024, 2)
        spec["vram_free_gb"] = 0.0
    return spec


@router.post("/selftest")
async def selftest(_user: dict[str, Any] = Depends(require_role("engineer"))) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # CUDA
    cuda_ok = False
    cuda_msg = "unavailable"
    try:
        import torch

        cuda_ok = bool(torch.cuda.is_available())
        cuda_msg = torch.cuda.get_device_name(0) if cuda_ok else "no CUDA"
    except Exception as exc:  # noqa: BLE001
        cuda_msg = str(exc)
    if _sim["active"] == "gpu_oom":
        cuda_ok = False
        cuda_msg = "SIMULATED: GPU OOM"
    checks.append({"name": "cuda", "ok": cuda_ok, "detail": cuda_msg})

    # Model
    from services.yolo_engine import WEIGHTS_DIR, get_yolo_engine

    best = WEIGHTS_DIR / "best.pt"
    model_ok = best.is_file() or any(WEIGHTS_DIR.glob("*.pt"))
    model_msg = str(best) if best.is_file() else "weights dir scan"
    if _sim["active"] == "model_missing":
        model_ok = False
        model_msg = "SIMULATED: model missing"
    else:
        try:
            eng = get_yolo_engine()
            model_ok = eng.mode == "ready" or model_ok
            model_msg = f"mode={eng.mode} model={eng.model_name}"
        except Exception as exc:  # noqa: BLE001
            model_ok = False
            model_msg = str(exc)
    checks.append({"name": "model", "ok": model_ok, "detail": model_msg})

    # Ollama
    from services.ollama_proxy import list_models

    if _sim["active"] == "ollama_offline":
        ollama = {"available": False, "message": "SIMULATED: Ollama offline", "models": []}
    else:
        ollama = list_models()
    checks.append(
        {
            "name": "ollama",
            "ok": bool(ollama.get("available")),
            "detail": ollama.get("message") or f"models={len(ollama.get('models') or [])}",
        }
    )

    # Disks
    disks_ok = True
    disk_detail = []
    for d in ("cache", "logs", "archive", "reports"):
        p = BASE_DIR / d
        p.mkdir(parents=True, exist_ok=True)
        ok = p.is_dir()
        disks_ok = disks_ok and ok
        disk_detail.append(f"{d}:{'ok' if ok else 'missing'}")
    checks.append({"name": "disks", "ok": disks_ok, "detail": ", ".join(disk_detail)})

    passed = all(c["ok"] for c in checks)
    return {"ok": passed, "checks": checks, "simulated": _sim["active"]}


class SimulateBody(BaseModel):
    type: str = Field(..., pattern=r"^(gpu_oom|model_missing|ollama_offline|clear)$")


@router.post("/simulate-failure")
async def simulate_failure(
    body: SimulateBody,
    _user: dict[str, Any] = Depends(require_role("engineer")),
) -> dict[str, Any]:
    if body.type == "clear":
        _sim["active"] = None
    else:
        _sim["active"] = body.type
    return {"ok": True, "active": _sim["active"]}


@router.get("/simulate-failure")
async def simulate_status(_user: dict[str, Any] = Depends(require_role("engineer"))) -> dict[str, Any]:
    return {"active": _sim["active"]}


# --- Detection inference config (SAHI slicing default + slice params) ---

class DetectConfigBody(BaseModel):
    use_sahi_default: bool = False
    slice_height: int = Field(default=512, ge=128, le=2048)
    slice_width: int = Field(default=512, ge=128, le=2048)
    overlap_ratio: float = Field(default=0.2, ge=0.0, le=0.5)
    # Response validator
    validator_enabled: bool = True
    validator_min_bbox_area: float = Field(default=0.0001, ge=0.0, le=0.9)
    validator_max_bbox_area: float = Field(default=0.9, ge=0.0, le=1.0)
    validator_min_confidence: float = Field(default=0.01, ge=0.0, le=1.0)
    # HUD exclusion
    hud_exclude_archive: bool = True
    hud_exclude_live: bool = False
    # YOLO backend: auto | torch | directml (experimental DirectML)
    yolo_inference_backend: str = Field(default="auto", pattern=r"^(auto|torch|directml)$")


def _read_detect_config() -> dict[str, Any]:
    from services.yolo_directml import directml_available

    backend = get_setting("yolo_inference_backend") or "auto"
    if backend not in ("auto", "torch", "directml"):
        backend = "auto"
    return {
        "use_sahi_default": (get_setting("use_sahi_default") or "0") == "1",
        "slice_height": int(get_setting("sahi_slice_height") or "512"),
        "slice_width": int(get_setting("sahi_slice_width") or "512"),
        "overlap_ratio": float(get_setting("sahi_overlap_ratio") or "0.2"),
        "validator_enabled": (get_setting("validator_enabled") or "1") == "1",
        "validator_min_bbox_area": float(get_setting("validator_min_bbox_area") or "0.0001"),
        "validator_max_bbox_area": float(get_setting("validator_max_bbox_area") or "0.9"),
        "validator_min_confidence": float(get_setting("validator_min_confidence") or "0.01"),
        "hud_exclude_archive": (get_setting("hud_exclude_archive") or "1") == "1",
        "hud_exclude_live": (get_setting("hud_exclude_live") or "0") == "1",
        "yolo_inference_backend": backend,
        "yolo_directml_available": directml_available(),
        "yolo_directml_preset": "YOLO DirectML (AMD/Intel GPU)",
    }


@router.get("/detect-config")
async def get_detect_config(
    _user: dict[str, Any] = Depends(require_role("engineer")),
) -> dict[str, Any]:
    return _read_detect_config()


@router.put("/detect-config")
async def put_detect_config(
    body: DetectConfigBody,
    _user: dict[str, Any] = Depends(require_role("engineer")),
) -> dict[str, Any]:
    set_setting("use_sahi_default", "1" if body.use_sahi_default else "0")
    set_setting("sahi_slice_height", str(body.slice_height))
    set_setting("sahi_slice_width", str(body.slice_width))
    set_setting("sahi_overlap_ratio", str(body.overlap_ratio))
    set_setting("validator_enabled", "1" if body.validator_enabled else "0")
    set_setting("validator_min_bbox_area", str(body.validator_min_bbox_area))
    set_setting("validator_max_bbox_area", str(body.validator_max_bbox_area))
    set_setting("validator_min_confidence", str(body.validator_min_confidence))
    set_setting("hud_exclude_archive", "1" if body.hud_exclude_archive else "0")
    set_setting("hud_exclude_live", "1" if body.hud_exclude_live else "0")
    set_setting("yolo_inference_backend", body.yolo_inference_backend)
    return _read_detect_config()
