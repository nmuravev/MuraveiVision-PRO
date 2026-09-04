"""One-at-a-time gsplat / bootstrap train for recon jobs (UI presets)."""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from services import recon_scanner
from services.gsplat_msvc import (
    MSVC_NEED_MSG,
    build_gsplat_launch,
    gsplat_train_ready,
)
from services.job_ids import sanitize_job_id
from services.runtime_log import write as runtime_write
from services.security import BASE_DIR
from services.train_presets import load_presets, total_vram_gb, used_vram_gb

RECON_ROOT = BASE_DIR / "archive" / "recon"
PY = BASE_DIR / "muravei_env" / "Scripts" / "python.exe"
BOOTSTRAP = BASE_DIR / "backend" / "scripts" / "bootstrap_model_ply.py"
TRAIN_JOB = BASE_DIR / "backend" / "scripts" / "gsplat_train_job.py"
PATCH_JIT = BASE_DIR / "scripts" / "patch_gsplat_windows_jit.py"

_lock = threading.Lock()
_proc: subprocess.Popen[str] | None = None
_thread: threading.Thread | None = None
_events: list[dict[str, Any]] = []
_state: dict[str, Any] = {
    "status": "idle",
    "job_id": None,
    "preset": None,
    "steps": 0,
    "max_steps": 0,
    "loss": None,
    "psnr": None,
    "vram_used_gb": 0.0,
    "vram_total_gb": 0.0,
    "eta_seconds": None,
    "message": "",
    "error": None,
    "artifact": None,
}


def _emit(ev: dict[str, Any]) -> None:
    with _lock:
        payload = {**_state, **ev, "ts": time.time()}
        for k, v in ev.items():
            if k in _state:
                _state[k] = v
        _events.append(payload)
        if len(_events) > 400:
            del _events[:200]


def drain_events(idx: int) -> tuple[list[dict[str, Any]], int]:
    with _lock:
        chunk = _events[idx:]
        return chunk, len(_events)


def status() -> dict[str, Any]:
    with _lock:
        st = dict(_state)
    st["vram_total_gb"] = round(total_vram_gb(), 2)
    st["vram_used_gb"] = round(max(used_vram_gb(), float(st.get("vram_used_gb") or 0)), 2)
    st["colmap_running"] = recon_scanner.status().get("status") == "running"
    return st


def _job_dir(job_id: str) -> Path:
    return RECON_ROOT / sanitize_job_id(job_id)


def _read_manifest(job_dir: Path) -> dict[str, Any]:
    path = job_dir / "manifest.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_manifest(job_dir: Path, data: dict[str, Any]) -> None:
    (job_dir / "manifest.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _patch_artifact(job_dir: Path, *, error: str | None = None) -> str | None:
    man = _read_manifest(job_dir)
    if error:
        man["status"] = "error"
        man["error"] = error
        _write_manifest(job_dir, man)
        return None
    artifact: str | None = None
    if (job_dir / "model.ply").is_file():
        artifact = "model.ply"
        man["status"] = "done"
        man["error"] = None
    elif (job_dir / "preview.ply").is_file():
        artifact = "preview.ply"
        if man.get("status") not in ("done",):
            man["status"] = "colmap_done"
    meta_path = job_dir / "gsplat_meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            artifact = meta.get("artifact") or artifact
        except json.JSONDecodeError:
            pass
    if artifact:
        man["artifact"] = artifact
        if artifact == "model.ply":
            man["status"] = "done"
            man["error"] = None
        _write_manifest(job_dir, man)
    return artifact


_STEP_RE = re.compile(r"(?:step|iter)[s\s:=]+(\d+)", re.I)
_LOSS_RE = re.compile(r"loss[=\s:]+([0-9.eE+-]+)", re.I)
_PSNR_RE = re.compile(r"psnr[=\s:]+([0-9.eE+-]+)", re.I)
_IMPORTANT_RE = re.compile(
    r"Error|Traceback|cl\.?exe|\bcl\b|CUDA|JIT|gsplat_train:|fatal|cannot find|MSVC|vcvars",
    re.I,
)


def format_train_error(code: int, lines: list[str]) -> str:
    """Human snippet from train log tail; always prefixes exit code."""
    base = f"exit code {code}"
    if not lines:
        return base
    important = [ln.strip() for ln in lines if ln.strip() and _IMPORTANT_RE.search(ln)]
    chosen = important[-3:] if important else [ln.strip() for ln in lines if ln.strip()][-3:]
    snippet = " | ".join(chosen)
    if len(snippet) > 280:
        snippet = snippet[:277] + "..."
    return f"{base}: {snippet}" if snippet else base


def _line_interesting(line: str) -> bool:
    return bool(
        _IMPORTANT_RE.search(line)
        or _STEP_RE.search(line)
        or _LOSS_RE.search(line)
        or _PSNR_RE.search(line)
    )


def _parse_line(line: str, max_steps: int) -> None:
    upd: dict[str, Any] = {}
    m = _STEP_RE.search(line)
    if m:
        steps = int(m.group(1))
        upd["steps"] = steps
        if max_steps > 0 and steps > 0:
            upd["eta_seconds"] = None
    m = _LOSS_RE.search(line)
    if m:
        try:
            upd["loss"] = float(m.group(1))
        except ValueError:
            pass
    m = _PSNR_RE.search(line)
    if m:
        try:
            upd["psnr"] = float(m.group(1))
        except ValueError:
            pass
    if upd:
        upd["vram_used_gb"] = round(used_vram_gb(), 2)
        upd["vram_total_gb"] = round(total_vram_gb(), 2)
        _emit(upd)


def _run_worker(job_id: str, preset_id: str, cfg: dict[str, Any]) -> None:
    global _proc
    job_dir = _job_dir(job_id)
    py = str(PY if PY.is_file() else Path(__import__("sys").executable))
    script = str(cfg.get("script") or "gsplat")
    max_steps = int(cfg.get("max_steps") or 0)
    t0 = time.time()
    log_path = job_dir / "train.log"
    ring: deque[str] = deque(maxlen=40)

    _emit(
        {
            "status": "training",
            "job_id": job_id,
            "preset": preset_id,
            "steps": 0,
            "max_steps": max_steps if script == "gsplat" else 1,
            "loss": None,
            "psnr": None,
            "message": f"Старт {preset_id}…",
            "error": None,
            "vram_total_gb": round(total_vram_gb(), 2),
            "vram_used_gb": round(used_vram_gb(), 2),
        }
    )

    env: dict[str, str] | None = None
    if script == "bootstrap":
        cmd = [
            py,
            str(BOOTSTRAP),
            "--job-dir",
            str(job_dir),
            "--max-points",
            str(int(cfg.get("max_points") or 80_000)),
        ]
    else:
        if PATCH_JIT.is_file():
            try:
                subprocess.run(
                    [py, str(PATCH_JIT)],
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                runtime_write("warn", "recon_train", f"JIT patch skip: {exc}")
        script_args = [
            str(TRAIN_JOB),
            "--job-dir",
            str(job_dir),
            "--max-steps",
            str(max_steps),
            "--data-factor",
            str(int(cfg.get("data_factor") or 4)),
        ]
        try:
            cmd, env = build_gsplat_launch(py, script_args, cwd=BASE_DIR)
        except RuntimeError as exc:
            err = str(exc)
            _patch_artifact(job_dir, error=err)
            _emit({"status": "error", "error": err, "message": f"Обучение не удалось: {err}"})
            runtime_write("error", "recon_train", f"preflight job={job_id} {err}")
            return

    runtime_write("info", "recon_train", f"start preset={preset_id} job={job_id}")
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log_f:
            proc = subprocess.Popen(
                cmd,
                cwd=str(BASE_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
            with _lock:
                _proc = proc
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip("\r\n")
                if not line:
                    continue
                ring.append(line)
                log_f.write(line + "\n")
                log_f.flush()
                _parse_line(line, max_steps)
                if _line_interesting(line):
                    msg = line if len(line) <= 240 else line[:237] + "..."
                    _emit({"message": msg})
                if max_steps > 0 and _state.get("steps"):
                    steps = int(_state["steps"] or 0)
                    elapsed = max(1.0, time.time() - t0)
                    rate = steps / elapsed
                    if rate > 0:
                        _emit({"eta_seconds": int(max(0, (max_steps - steps) / rate))})
            code = proc.wait()
        with _lock:
            _proc = None
        if code != 0:
            err = format_train_error(code, list(ring))
            _patch_artifact(job_dir, error=err)
            _emit(
                {
                    "status": "error",
                    "error": err,
                    "message": f"Обучение не удалось: {err}",
                }
            )
            runtime_write("error", "recon_train", f"fail job={job_id} {err}")
            return
        artifact = _patch_artifact(job_dir)
        if not artifact:
            err = "нет model.ply / preview.ply после обучения"
            _patch_artifact(job_dir, error=err)
            _emit({"status": "error", "error": err, "message": f"Обучение не удалось: {err}"})
            return
        _emit(
            {
                "status": "done",
                "artifact": artifact,
                "steps": max_steps or 1,
                "max_steps": max_steps or 1,
                "message": f"Готово · {artifact}",
                "error": None,
                "eta_seconds": 0,
            }
        )
        runtime_write("info", "recon_train", f"done job={job_id} artifact={artifact}")
    except Exception as exc:  # noqa: BLE001
        with _lock:
            _proc = None
        err = str(exc)
        _patch_artifact(job_dir, error=err)
        _emit({"status": "error", "error": err, "message": f"Обучение не удалось: {err}"})
        runtime_write("error", "recon_train", f"exception job={job_id}: {err}")


def start(job_id: str, preset: str) -> dict[str, Any]:
    global _thread
    job_id = sanitize_job_id(job_id)
    job_dir = _job_dir(job_id)
    if not job_dir.is_dir():
        raise FileNotFoundError(f"job not found: {job_id}")
    man = _read_manifest(job_dir)
    if str(man.get("status") or "") == "running":
        raise RuntimeError("Дождитесь завершения COLMAP")
    if recon_scanner.status().get("status") == "running":
        raise RuntimeError("Дождитесь завершения COLMAP")

    presets, _ = load_presets()
    if preset not in presets:
        raise ValueError(f"unknown preset: {preset}")
    cfg = presets[preset]
    script = str(cfg.get("script") or "gsplat")
    if script == "gsplat":
        ok, reason = gsplat_train_ready()
        if not ok:
            raise RuntimeError(reason or MSVC_NEED_MSG)
    min_v = float(cfg.get("min_vram_gb") or 0)
    vram = total_vram_gb()
    if min_v and (vram <= 0 or vram < min_v):
        raise RuntimeError(
            f"Пресет {preset} требует ≥{min_v:g} ГБ VRAM (сейчас {vram:.1f} ГБ)"
        )

    with _lock:
        alive = bool(_thread and _thread.is_alive())
        if _state["status"] == "training" or alive:
            raise RuntimeError("Обучение уже выполняется")
        _events.clear()
        _thread = threading.Thread(
            target=_run_worker,
            args=(job_id, preset, cfg),
            name=f"recon-train-{job_id}",
            daemon=True,
        )
        _thread.start()
    return status()


def stop() -> dict[str, Any]:
    global _proc
    with _lock:
        proc = _proc
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    with _lock:
        _proc = None
        if _state["status"] == "training":
            _state["status"] = "idle"
            _state["message"] = "Остановлено"
    _emit({"status": "idle", "message": "Остановлено"})
    return status()
