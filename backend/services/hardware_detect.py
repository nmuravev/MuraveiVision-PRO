"""Hardware component detection + portable tier classification (Z5).

Paths are repo-relative or overridden via ``MURAVEI_*`` env vars (Z1).
Tier thresholds live in ``config/hardware_tiers.json``.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from services.security import BASE_DIR

_LOG = logging.getLogger("muravei.hardware_detect")

_TIERS_PATH = BASE_DIR / "config" / "hardware_tiers.json"
_PROFILE_PATH = BASE_DIR / "config" / "local" / "hardware_profile.json"


def _env_path(name: str) -> Path | None:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None
    return Path(raw)


def _repo_path(*parts: str) -> Path:
    return BASE_DIR.joinpath(*parts)


def detect_python() -> dict[str, Any]:
    override = _env_path("MURAVEI_PYTHON")
    candidates: list[Path] = []
    if override:
        candidates.append(override)
    candidates.extend(
        [
            _repo_path("muravei_env", "Scripts", "python.exe"),
            _repo_path("muravei_env", "bin", "python"),
            _repo_path("muravei_env", "python.exe"),
        ]
    )
    for p in candidates:
        if p.is_file():
            return {"present": True, "path": str(p), "relative": _rel_or_env(p)}
    return {"present": False, "path": None, "relative": None}


def detect_ffmpeg() -> dict[str, Any]:
    override = _env_path("MURAVEI_FFMPEG_DIR")
    roots: list[Path] = []
    if override:
        roots.append(override)
    roots.append(_repo_path("assets", "ffmpeg"))
    roots.append(_repo_path("assets"))
    for root in roots:
        for name in ("ffmpeg.exe", "ffmpeg"):
            cand = root / name
            if cand.is_file():
                return {"present": True, "path": str(cand), "relative": _rel_or_env(cand)}
    which = shutil.which("ffmpeg")
    if which:
        return {"present": True, "path": which, "relative": "PATH"}
    return {"present": False, "path": None, "relative": None}


def detect_colmap() -> dict[str, Any]:
    override = _env_path("MURAVEI_SIDECARS_DIR")
    roots: list[Path] = []
    if override:
        roots.append(Path(override) / "colmap")
    env_root = (os.environ.get("COLMAP_ROOT") or "").strip()
    if env_root:
        roots.append(Path(env_root))
    roots.append(_repo_path("sidecars", "colmap"))
    names = ("COLMAP.bat", "colmap.exe", "bin/colmap.exe", "colmap")
    for root in roots:
        for name in names:
            cand = root / name if "/" not in name else root.joinpath(*name.split("/"))
            if cand.is_file():
                return {"present": True, "path": str(cand), "relative": _rel_or_env(cand)}
    return {"present": False, "path": None, "relative": None}


def detect_alicevision() -> dict[str, Any]:
    override = _env_path("MURAVEI_SIDECARS_DIR")
    roots: list[Path] = []
    env_root = (os.environ.get("ALICEVISION_ROOT") or "").strip()
    if env_root:
        roots.append(Path(env_root))
    if override:
        roots.append(Path(override) / "alicevision" / "windows-x64")
    roots.append(_repo_path("sidecars", "alicevision", "windows-x64"))
    tool = "aliceVision_featureExtraction.exe"
    for root in roots:
        cand = root / "bin" / tool
        if cand.is_file():
            return {"present": True, "path": str(cand), "relative": _rel_or_env(cand)}
        cand2 = root / tool
        if cand2.is_file():
            return {"present": True, "path": str(cand2), "relative": _rel_or_env(cand2)}
    return {"present": False, "path": None, "relative": None}


def detect_gpu() -> dict[str, Any]:
    """CUDA presence for tiering (not torch install state)."""
    forced = (os.environ.get("MURAVEI_FORCE_ACCELERATOR") or "").strip().lower()
    if forced == "cuda":
        return {"present": True, "cuda": True, "source": "env"}
    if forced == "cpu":
        return {"present": False, "cuda": False, "source": "env"}
    try:
        import torch

        ok = bool(torch.cuda.is_available())
        return {
            "present": ok,
            "cuda": ok,
            "source": "torch",
            "torch_cuda": getattr(getattr(torch, "version", None), "cuda", None),
        }
    except Exception:  # noqa: BLE001
        pass
    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        return {"present": True, "cuda": True, "source": "nvidia-smi"}
    return {"present": False, "cuda": False, "source": "none"}


def _rel_or_env(path: Path) -> str:
    try:
        return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()
    except Exception:  # noqa: BLE001
        return str(path)


def _load_tiers_config() -> dict[str, Any]:
    if not _TIERS_PATH.is_file():
        return {
            "tiers": {
                "2": {"require_cuda": True, "min_ram_gb": 16, "min_cpu_cores": 8, "label_ru": "полевая станция"},
                "1": {"require_cuda": False, "min_ram_gb_or": 16, "min_cpu_cores_or": 8, "label_ru": "рабочая станция"},
                "0": {"label_ru": "офис"},
            }
        }
    return json.loads(_TIERS_PATH.read_text(encoding="utf-8"))


def _ram_gb_and_cores() -> tuple[float, int]:
    ram_gb = 0.0
    cores = 0
    try:
        import psutil

        ram_gb = float(psutil.virtual_memory().total) / (1024**3)
        cores = int(psutil.cpu_count() or 0)
    except Exception:  # noqa: BLE001
        pass
    return ram_gb, cores


def classify_tier(
    *,
    cuda: bool | None = None,
    ram_gb: float | None = None,
    cores: int | None = None,
) -> dict[str, Any]:
    """Return tier 0|1|2 + reasons. Honors ``MURAVEI_FORCE_TIER``."""
    forced = (os.environ.get("MURAVEI_FORCE_TIER") or "").strip()
    cfg = _load_tiers_config()
    tiers = cfg.get("tiers") or {}
    if forced in ("0", "1", "2"):
        t = int(forced)
        label = (tiers.get(str(t)) or {}).get("label_ru") or f"tier {t}"
        return {
            "tier": t,
            "label_ru": label,
            "reasons": [f"MURAVEI_FORCE_TIER={forced}"],
            "forced": True,
        }

    if cuda is None:
        cuda = bool(detect_gpu().get("cuda"))
    if ram_gb is None or cores is None:
        r, c = _ram_gb_and_cores()
        if ram_gb is None:
            ram_gb = r
        if cores is None:
            cores = c

    t2 = tiers.get("2") or {}
    reasons: list[str] = []
    if (
        bool(t2.get("require_cuda", True))
        and cuda
        and ram_gb >= float(t2.get("min_ram_gb", 16))
        and cores >= int(t2.get("min_cpu_cores", 8))
    ):
        reasons.append(f"cuda + ram>={t2.get('min_ram_gb', 16)} + cores>={t2.get('min_cpu_cores', 8)}")
        return {
            "tier": 2,
            "label_ru": t2.get("label_ru") or "полевая станция",
            "reasons": reasons,
            "forced": False,
            "ram_gb": round(ram_gb, 1),
            "cores": cores,
            "cuda": cuda,
        }

    t1 = tiers.get("1") or {}
    if not cuda and (
        ram_gb >= float(t1.get("min_ram_gb_or", 16)) or cores >= int(t1.get("min_cpu_cores_or", 8))
    ):
        reasons.append(
            f"no cuda + (ram>={t1.get('min_ram_gb_or', 16)} or cores>={t1.get('min_cpu_cores_or', 8)})"
        )
        return {
            "tier": 1,
            "label_ru": t1.get("label_ru") or "рабочая станция",
            "reasons": reasons,
            "forced": False,
            "ram_gb": round(ram_gb, 1),
            "cores": cores,
            "cuda": cuda,
        }

    t0 = tiers.get("0") or {}
    reasons.append("below tier 1/2 thresholds")
    return {
        "tier": 0,
        "label_ru": t0.get("label_ru") or "офис",
        "reasons": reasons,
        "forced": False,
        "ram_gb": round(ram_gb, 1),
        "cores": cores,
        "cuda": cuda,
    }


def load_hardware_profile() -> dict[str, Any] | None:
    if not _PROFILE_PATH.is_file():
        return None
    try:
        return json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def detect_all() -> dict[str, Any]:
    from config import read_kit

    gpu = detect_gpu()
    tier = classify_tier(cuda=bool(gpu.get("cuda")))
    profile = load_hardware_profile() or {}
    kit = read_kit()
    build_profile = (
        str(profile.get("build_profile") or profile.get("profile") or "").strip()
        or (kit if kit != "dev" else None)
        or kit
    )
    mismatch_info = _mismatch_message(build_profile, int(tier["tier"]))
    return {
        "gpu": gpu,
        "python": detect_python(),
        "ffmpeg": detect_ffmpeg(),
        "colmap": detect_colmap(),
        "alicevision": detect_alicevision(),
        "tier": tier,
        "build_profile": build_profile,
        "kit": kit,
        "mismatch": mismatch_info,
        "badge_ru": _badge_ru(build_profile, tier),
    }


def _mismatch_message(build_profile: str | None, tier: int) -> dict[str, Any] | None:
    """Inform never block (Z5)."""
    if not build_profile:
        return None
    bp = build_profile.lower()
    if bp == "mini" and tier >= 2:
        return {
            "level": "info",
            "message_ru": "Full разблокирует splat/dense — сейчас Mini-сборка на мощном железе",
        }
    if bp == "full" and tier <= 0:
        return {
            "level": "warning",
            "message_ru": "Full на слабом железе — применены CPU-капы; работа продолжится",
        }
    return None


def _badge_ru(build_profile: str | None, tier: dict[str, Any]) -> str:
    raw = (build_profile or "dev").strip().lower()
    build = {"mini": "Mini", "full": "Full", "dev": "dev"}.get(raw, raw.capitalize())
    label = tier.get("label_ru") or "класс"
    return f"Сборка: {build} · класс: {label} (tier {tier.get('tier', '?')})"


def log_detect_once() -> dict[str, Any]:
    snap = detect_all()
    _LOG.info(
        "hardware_detect tier=%s build=%s badge=%s",
        snap.get("tier", {}).get("tier"),
        snap.get("build_profile"),
        snap.get("badge_ru"),
    )
    print(f"[SYSTEM] {snap.get('badge_ru')}")
    mismatch = snap.get("mismatch")
    if mismatch:
        print(f"[SYSTEM] [{mismatch.get('level')}] {mismatch.get('message_ru')}")
    return snap
