"""Portable bootstrap helpers: venv audit/self-heal (Z2) + fingerprint.

Filesystem paths are repo-relative or ``MURAVEI_*`` overrides (Z1).
Download URLs/sha256 live only in ``scripts/portable_manifest.json``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from services.security import BASE_DIR

_REQ = BASE_DIR / "backend" / "requirements.txt"
_MANIFEST = BASE_DIR / "scripts" / "portable_manifest.json"
_STAMP = BASE_DIR / "config" / "local" / "bootstrap_complete.json"
_PROFILE = BASE_DIR / "config" / "local" / "hardware_profile.json"
_VENV_WIN = BASE_DIR / "muravei_env" / "Scripts" / "python.exe"
_VENV_NIX = BASE_DIR / "muravei_env" / "bin" / "python"
_PYVENV_CFG = BASE_DIR / "muravei_env" / "pyvenv.cfg"


def wheels_dir() -> Path:
    override = (os.environ.get("MURAVEI_WHEELS_DIR") or "").strip()
    if override:
        return Path(override)
    return BASE_DIR / "wheels"


def venv_python() -> Path | None:
    override = (os.environ.get("MURAVEI_PYTHON") or "").strip()
    if override and Path(override).is_file():
        return Path(override)
    if _VENV_WIN.is_file():
        return _VENV_WIN
    if _VENV_NIX.is_file():
        return _VENV_NIX
    alt = BASE_DIR / "muravei_env" / "python.exe"
    if alt.is_file():
        return alt
    return None


def requirements_hash() -> str:
    if not _REQ.is_file():
        return ""
    return hashlib.sha256(_REQ.read_bytes()).hexdigest()


def load_portable_manifest() -> dict[str, Any]:
    if not _MANIFEST.is_file():
        return {}
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def resolve_build_profile() -> str:
    forced = (os.environ.get("MURAVEI_BUILD_PROFILE") or "").strip().lower()
    if forced in ("mini", "full"):
        return forced
    existing = None
    if _PROFILE.is_file():
        try:
            existing = json.loads(_PROFILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            existing = None
    if existing:
        bp = str(existing.get("build_profile") or existing.get("profile") or "").lower()
        if bp in ("mini", "full"):
            return bp
    man = load_portable_manifest()
    default = str((man.get("default_profile") or "mini")).lower()
    return default if default in ("mini", "full") else "mini"


def interpreter_alive(py: Path | None = None) -> bool:
    py = py or venv_python()
    if py is None or not py.is_file():
        return False
    try:
        proc = subprocess.run(
            [str(py), "-c", "import sys; print('%d.%d'%sys.version_info[:2])"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            return False
        ver = (proc.stdout or "").strip()
        return ver.startswith("3.12")
    except Exception:  # noqa: BLE001
        return False


def pyvenv_cfg_valid() -> bool:
    """True when pyvenv.cfg missing (embeddable) or home looks usable."""
    if not _PYVENV_CFG.is_file():
        # Embeddable portable often has no pyvenv.cfg — OK if python runs.
        return True
    try:
        text = _PYVENV_CFG.read_text(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return False
    home = None
    for line in text.splitlines():
        if line.strip().lower().startswith("home"):
            parts = line.split("=", 1)
            if len(parts) == 2:
                home = parts[1].strip()
            break
    if not home:
        return True
    home_path = Path(home)
    # Broken when home points at a missing directory
    if not home_path.is_dir():
        return False
    return True


def env_status() -> str:
    """absent | broken | alive"""
    py = venv_python()
    if py is None:
        return "absent"
    if not interpreter_alive(py):
        return "broken"
    if not pyvenv_cfg_valid():
        return "broken"
    return "alive"


def _parse_req_names(req_text: str) -> list[str]:
    names: list[str] = []
    for line in req_text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("-"):
            continue
        # strip extras / markers
        s = s.split(";", 1)[0].strip()
        m = re.match(r"^([A-Za-z0-9_.\-]+)", s)
        if m:
            names.append(m.group(1).lower().replace("_", "-"))
    return names


def pip_freeze(py: Path) -> dict[str, str]:
    proc = subprocess.run(
        [str(py), "-m", "pip", "freeze"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    out: dict[str, str] = {}
    if proc.returncode != 0:
        return out
    for line in (proc.stdout or "").splitlines():
        if "==" not in line:
            continue
        name, ver = line.split("==", 1)
        out[name.strip().lower().replace("_", "-")] = ver.strip()
    return out


def missing_packages(py: Path | None = None) -> list[str]:
    py = py or venv_python()
    if py is None or not _REQ.is_file():
        return []
    req_names = _parse_req_names(_REQ.read_text(encoding="utf-8"))
    installed = pip_freeze(py)
    missing: list[str] = []
    for name in req_names:
        # nvidia-ml-py installs as nvidia-ml-py / pynvml
        aliases = {name}
        if name == "nvidia-ml-py":
            aliases.add("pynvml")
        if name == "opencv-python-headless":
            aliases.add("opencv-python-headless")
        if name.startswith("uvicorn"):
            aliases.add("uvicorn")
        if not any(a in installed for a in aliases):
            missing.append(name)
    return missing


def torch_variant(py: Path | None = None) -> dict[str, Any]:
    py = py or venv_python()
    if py is None:
        return {"installed": False, "cuda": None}
    code = (
        "import json\n"
        "try:\n"
        " import torch\n"
        " print(json.dumps({'installed': True, 'cuda': torch.version.cuda, "
        "'cuda_available': bool(torch.cuda.is_available()), 'version': torch.__version__}))\n"
        "except Exception as e:\n"
        " print(json.dumps({'installed': False, 'cuda': None, 'error': str(e)}))\n"
    )
    try:
        proc = subprocess.run(
            [str(py), "-c", code],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            return {"installed": False, "cuda": None}
        return json.loads((proc.stdout or "").strip() or "{}")
    except Exception as exc:  # noqa: BLE001
        return {"installed": False, "cuda": None, "error": str(exc)}


def gpu_present() -> bool:
    try:
        from services.hardware_detect import detect_gpu

        return bool(detect_gpu().get("cuda"))
    except Exception:  # noqa: BLE001
        return False


def compute_fingerprint(
    *,
    build_profile: str | None = None,
    component_versions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tv = torch_variant()
    variant = "cuda" if tv.get("cuda") else ("cpu" if tv.get("installed") else "none")
    return {
        "requirements_sha256": requirements_hash(),
        "torch_variant": variant,
        "torch_version": tv.get("version"),
        "gpu_present": gpu_present(),
        "build_profile": build_profile or resolve_build_profile(),
        "component_versions": component_versions or {},
    }


def stamp_matches(expected: dict[str, Any] | None = None) -> bool:
    if not _STAMP.is_file():
        return False
    try:
        stamp = json.loads(_STAMP.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    fp = stamp.get("fingerprint") or {}
    want = expected or compute_fingerprint(
        build_profile=str(stamp.get("build_profile") or resolve_build_profile()),
        component_versions=fp.get("component_versions") or {},
    )
    keys = ("requirements_sha256", "torch_variant", "gpu_present", "build_profile")
    for k in keys:
        if fp.get(k) != want.get(k):
            return False
    return True


def write_stamp(
    *,
    build_profile: str,
    messages: list[str] | None = None,
    component_versions: dict[str, Any] | None = None,
) -> Path:
    _STAMP.parent.mkdir(parents=True, exist_ok=True)
    fp = compute_fingerprint(build_profile=build_profile, component_versions=component_versions)
    payload = {
        "schema_version": 1,
        "build_profile": build_profile,
        "fingerprint": fp,
        "messages": messages or [],
    }
    _STAMP.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return _STAMP


def apply_hardware_profile(build_profile: str, tier: dict[str, Any] | None = None) -> Path:
    man = load_portable_manifest()
    profiles = man.get("profiles") or {}
    cfg = dict(profiles.get(build_profile) or {})
    cfg["build_profile"] = build_profile
    if tier:
        cfg["tier"] = tier.get("tier")
        cfg["tier_label_ru"] = tier.get("label_ru")
    # Mismatch: inform never block — Full on weak HW applies CPU caps hint
    if build_profile == "full" and tier and int(tier.get("tier") or 0) <= 0:
        cfg.setdefault("cpu_caps_applied", True)
        cfg.setdefault(
            "warning_ru",
            "Full на слабом железе — применены CPU-капы; работа продолжится",
        )
    if build_profile == "mini" and tier and int(tier.get("tier") or 0) >= 2:
        cfg.setdefault(
            "info_ru",
            "Full разблокирует splat/dense — сейчас Mini-сборка на мощном железе",
        )
    _PROFILE.parent.mkdir(parents=True, exist_ok=True)
    _PROFILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return _PROFILE


def remove_broken_env() -> None:
    env_dir = BASE_DIR / "muravei_env"
    if env_dir.is_dir():
        shutil.rmtree(env_dir, ignore_errors=True)


def install_requirements_offline_first(py: Path) -> dict[str, Any]:
    """Install/repair packages: wheels/ first, else network (Z3)."""
    wdir = wheels_dir()
    has_wheels = wdir.is_dir() and any(wdir.glob("*.whl"))
    cmd_base = [str(py), "-m", "pip", "install"]
    if has_wheels:
        cmd = cmd_base + ["--no-index", f"--find-links={wdir}", "-r", str(_REQ)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, check=False)
        if proc.returncode == 0:
            return {"ok": True, "mode": "offline_wheels", "stdout": proc.stdout[-2000:]}
        # fall through to network if allowed
    online = (os.environ.get("MURAVEI_BOOTSTRAP_ONLINE") or "1").strip() != "0"
    if not online and not has_wheels:
        return {
            "ok": False,
            "mode": "none",
            "error_ru": (
                "Нет wheels/ и сеть отключена. Привезите папку wheels/ "
                "(или muravei_env_pack.zip) рядом с проектом."
            ),
        }
    if not online:
        return {
            "ok": False,
            "mode": "offline_failed",
            "error_ru": "Офлайн-установка из wheels/ не удалась. Обновите wheels/.",
        }
    proc = subprocess.run(
        cmd_base + ["--no-cache-dir", "-r", str(_REQ)],
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if proc.returncode != 0:
        return {
            "ok": False,
            "mode": "network",
            "error_ru": "pip install из сети не удался.",
            "stderr": (proc.stderr or "")[-2000:],
        }
    return {"ok": True, "mode": "network", "stdout": (proc.stdout or "")[-2000:]}


def reconcile_torch(py: Path, build_profile: str) -> dict[str, Any]:
    """CUDA machine + full + torch CPU → try CUDA wheels; mini keeps CPU + info."""
    tv = torch_variant(py)
    cuda_hw = gpu_present()
    messages: list[str] = []
    if build_profile == "mini":
        if cuda_hw and tv.get("cuda") is None and tv.get("installed"):
            messages.append("Mini: оставляем torch CPU; Full разблокирует CUDA-вариант")
        return {"ok": True, "action": "keep", "messages": messages, "torch": tv}

    if cuda_hw and tv.get("installed") and tv.get("cuda") is None:
        wdir = wheels_dir()
        has_wheels = wdir.is_dir() and any(wdir.glob("torch-*.whl"))
        if has_wheels:
            proc = subprocess.run(
                [str(py), "-m", "pip", "install", "--no-index", f"--find-links={wdir}", "torch", "torchvision"],
                capture_output=True,
                text=True,
                timeout=1800,
                check=False,
            )
            if proc.returncode == 0:
                messages.append("Установлен CUDA torch из wheels/")
                return {"ok": True, "action": "installed_cuda_wheels", "messages": messages}
        # network index from manifest if present
        man = load_portable_manifest()
        torch_cfg = ((man.get("components") or {}).get("torch_cuda") or {})
        index = torch_cfg.get("index_url")
        if index and (os.environ.get("MURAVEI_BOOTSTRAP_ONLINE") or "1").strip() != "0":
            proc = subprocess.run(
                [
                    str(py),
                    "-m",
                    "pip",
                    "install",
                    "--index-url",
                    str(index),
                    "torch",
                    "torchvision",
                ],
                capture_output=True,
                text=True,
                timeout=1800,
                check=False,
            )
            if proc.returncode == 0:
                messages.append("Установлен CUDA torch из сети")
                return {"ok": True, "action": "installed_cuda_network", "messages": messages}
        messages.append("Нужен CUDA torch, но wheels/сети недостаточно — продолжаем с CPU")
        return {"ok": True, "action": "cpu_fallback", "messages": messages, "torch": tv}
    return {"ok": True, "action": "noop", "messages": messages, "torch": tv}


def audit_env(build_profile: str | None = None) -> dict[str, Any]:
    """Run Z2 audit; returns status + actions needed (does not call setup_env)."""
    bp = build_profile or resolve_build_profile()
    status = env_status()
    result: dict[str, Any] = {
        "build_profile": bp,
        "env_status": status,
        "needs_full_rebuild": status in ("absent", "broken"),
        "missing_packages": [],
        "torch": {},
        "messages": [],
    }
    if status != "alive":
        if status == "broken":
            result["messages"].append("Битый muravei_env — требуется полная пересборка (не skip)")
        else:
            result["messages"].append("muravei_env отсутствует — требуется создание")
        return result

    py = venv_python()
    assert py is not None
    missing = missing_packages(py)
    result["missing_packages"] = missing
    if missing:
        result["messages"].append(f"Неполные пакеты: {', '.join(missing[:12])}")
    result["torch"] = torch_variant(py)
    return result


def heal_env(build_profile: str | None = None) -> dict[str, Any]:
    """Self-heal incomplete env packages + torch variant (assumes env alive)."""
    bp = build_profile or resolve_build_profile()
    py = venv_python()
    if py is None or not interpreter_alive(py):
        return {"ok": False, "error_ru": "Интерпретатор недоступен — нужен полный rebuild"}
    messages: list[str] = []
    missing = missing_packages(py)
    if missing:
        inst = install_requirements_offline_first(py)
        if not inst.get("ok"):
            return {"ok": False, **inst}
        messages.append(f"Доустановлены пакеты ({inst.get('mode')})")
        still = missing_packages(py)
        if still:
            return {
                "ok": False,
                "error_ru": f"После установки всё ещё нет: {', '.join(still[:12])}",
            }
    torch_res = reconcile_torch(py, bp)
    messages.extend(torch_res.get("messages") or [])
    return {"ok": True, "messages": messages, "torch": torch_res}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sha256(path: Path, expected: str) -> bool:
    exp = (expected or "").strip().lower()
    if not exp:
        return False
    return sha256_file(path) == exp


def cli_audit() -> int:
    """CLI entry for bootstrap scripts: print JSON audit to stdout."""
    bp = resolve_build_profile()
    data = audit_env(bp)
    data["fingerprint"] = compute_fingerprint(build_profile=bp)
    data["stamp_ok"] = stamp_matches()
    print(json.dumps(data, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    # Allow: muravei_env\Scripts\python.exe -m services.portable_bootstrap
    # when PYTHONPATH=backend
    cmd = sys.argv[1] if len(sys.argv) > 1 else "audit"
    if cmd == "audit":
        raise SystemExit(cli_audit())
    if cmd == "heal":
        print(json.dumps(heal_env(), ensure_ascii=False))
        raise SystemExit(0)
    if cmd == "fingerprint":
        print(json.dumps(compute_fingerprint(), ensure_ascii=False))
        raise SystemExit(0)
    print(f"Unknown command: {cmd}", file=sys.stderr)
    raise SystemExit(2)
