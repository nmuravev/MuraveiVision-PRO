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
from services.alicevision import alicevision_available, alicevision_cuda_ready
from services.alicevision_pipeline import (
    normalize_artifacts,
    patch_manifest_artifacts,
    run_dense_pipeline,
)
from services.gsplat_msvc import (
    MSVC_NEED_MSG,
    build_gsplat_launch,
    gsplat_train_ready,
)
from services.job_ids import sanitize_job_id
from services.runtime_log import write as runtime_write
from services.security import BASE_DIR
from services.train_presets import load_presets, total_vram_gb, used_vram_gb

_AV_SCRIPTS = frozenset({"alicevision_mvs", "alicevision_mesh"})

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

def _recover_stale_training_unlocked() -> bool:
    """If status is training but worker thread/proc are dead, surface error + unlock.

    Caller holds _lock. Mirrors recon_scanner stale-running recovery so a killed
    uvicorn / orphaned child cannot leave the UI stuck on «training · 0/N».
    """
    global _thread, _proc
    if _state.get("status") != "training":
        return False
    alive = bool(_thread and _thread.is_alive())
    proc = _proc
    proc_alive = bool(proc is not None and proc.poll() is None)
    if alive or proc_alive:
        return False
    job_id = str(_state.get("job_id") or "")
    err = (
        "обучение прервано (процесс train не найден — перезапуск backend / Stop). "
        "Запустите Balanced ещё раз."
    )
    runtime_write(
        "warn",
        "recon_train",
        f"stale training recovered job={job_id or '?'}",
    )
    if job_id:
        try:
            _patch_artifact(_job_dir(job_id), error=err)
        except OSError:
            pass
    _proc = None
    _thread = None
    _state["status"] = "error"
    _state["error"] = err
    _state["message"] = f"Обучение не удалось: {err}"
    _events.append({**_state, "ts": time.time()})
    if len(_events) > 400:
        del _events[:200]
    return True

def status() -> dict[str, Any]:
    with _lock:
        _recover_stale_training_unlocked()
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
        # Failed/interrupted train must not lock out Balanced retry (isReconReady).
        # Keep prior model.ply as done; else fall back to colmap_done when sparse exists.
        man["last_train_error"] = error
        has_model = (job_dir / "model.ply").is_file()
        sparse0 = job_dir / "colmap" / "sparse" / "0"
        has_sparse = (sparse0 / "points3D.bin").is_file() or (sparse0 / "points3D.txt").is_file()
        if has_model:
            man["status"] = "done"
            man["artifact"] = "model.ply"
            man["error"] = None
        elif has_sparse or (job_dir / "preview.ply").is_file():
            man["status"] = "colmap_done"
            man["error"] = None
        else:
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
            # Clear sparse CTA — otherwise Flight3D keeps «нужен train» after Balanced.
            man.pop("next_action", None)
            man.pop("last_train_error", None)
        _write_manifest(job_dir, man)
    return artifact

_STEP_RE = re.compile(r"(?:step|iter)[s\s:=]+(\d+)", re.I)
# gsplat/tqdm: "loss=0.13| sh degree=0| :  30%|███| 2123/7000 [00:21<…]"
_TQDM_STEP_RE = re.compile(r"\|\s*(\d+)\s*/\s*(\d+)\b")
_LOSS_RE = re.compile(r"loss[=\s:]+([0-9.eE+-]+)", re.I)
_PSNR_RE = re.compile(r"psnr[=\s:]+([0-9.eE+-]+)", re.I)
_IMPORTANT_RE = re.compile(
    r"Error|Traceback|cl\.?exe|\bcl\b|CUDA|JIT|gsplat_train:|fatal|cannot find|MSVC|vcvars|"
    r"Model initialized|Downscaling|Scene scale|vcvarsall|Developer Command",
    re.I,
)
_PREP_MSG_RE = re.compile(
    r"vcvars|Developer Command|Downscaling|Scene scale|Model initialized|Parser\]",
    re.I,
)

def format_train_error(code: int, lines: list[str]) -> str:
    """Human snippet from train log tail; always prefixes exit code."""
    # Windows STATUS_CONTROL_C_EXIT — uvicorn reload / Ctrl+C / console close
    # Compare unsigned 32-bit: wait() may return signed (-1073741510) or unsigned.
    code_u32 = int(code) & 0xFFFFFFFF
    if code_u32 == 0xC000013A or int(code) in (3221225786, -1073741510):
        return (
            f"exit code {code}: обучение прервано (Ctrl+C / reload backend). "
            "Запустите Balanced ещё раз без --reload (npm run backend, не backend:watch)."
        )
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
        or _TQDM_STEP_RE.search(line)
        or _LOSS_RE.search(line)
        or _PSNR_RE.search(line)
    )

def _parse_line(line: str, max_steps: int) -> None:
    upd: dict[str, Any] = {}
    m = _STEP_RE.search(line)
    if m:
        steps = int(m.group(1))
        upd["steps"] = steps
    tm = _TQDM_STEP_RE.search(line)
    if tm:
        steps = int(tm.group(1))
        total = int(tm.group(2))
        # Ignore data-prep bars like "121/121" downscale; only train bars
        # (denominator matches preset max_steps) or lines that also carry loss=.
        is_train_bar = (max_steps > 0 and total == max_steps) or bool(_LOSS_RE.search(line))
        if is_train_bar:
            prev = int(upd.get("steps") or 0)
            if steps >= prev:
                upd["steps"] = steps
            if total > 0:
                upd["max_steps"] = total
    if "steps" in upd and int(upd["steps"] or 0) > 0:
        upd["eta_seconds"] = None
        if int(_state.get("steps") or 0) == 0:
            upd["message"] = f"Обучение gsplat · {upd['steps']}/{upd.get('max_steps') or max_steps or '?'} шагов"
    elif _PREP_MSG_RE.search(line):
        short = line if len(line) <= 200 else line[:197] + "..."
        upd["message"] = short
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

def _run_sparse_select_worker(job_id: str, preset_id: str) -> None:
    """Mark sparse artifact selected — no dense/splat work."""
    job_dir = _job_dir(job_id)
    _emit(
        {
            "status": "training",
            "job_id": job_id,
            "preset": preset_id,
            "steps": 0,
            "max_steps": 1,
            "message": "Выбор sparse COLMAP…",
            "error": None,
        }
    )
    man = _read_manifest(job_dir)
    man = normalize_artifacts(man)
    sparse_file = str(man.get("sparse_file") or "sparse_points.json")
    if not (job_dir / sparse_file).is_file() and not (job_dir / "colmap" / "sparse" / "0").is_dir():
        err = "Нет sparse COLMAP для этого job"
        _emit({"status": "error", "error": err, "message": err})
        return
    arts = dict(man.get("artifacts") or {})
    arts["sparse"] = {"file": sparse_file}
    man["artifacts"] = arts
    man["selected_artifact"] = "sparse"
    man["artifact"] = None
    man["status"] = "colmap_done"
    man["next_action"] = "balanced_for_splat"
    _write_manifest(job_dir, man)
    _emit(
        {
            "status": "done",
            "steps": 1,
            "max_steps": 1,
            "artifact": sparse_file,
            "message": "Sparse COLMAP выбран",
            "error": None,
        }
    )


def _run_alicevision_worker(job_id: str, preset_id: str, cfg: dict[str, Any]) -> None:
    """Dense / mesh via AliceVision; never wipe COLMAP sparse on failure."""
    job_dir = _job_dir(job_id)
    script = str(cfg.get("script") or "alicevision_mvs")
    mode = "mesh" if script == "alicevision_mesh" else "dense"
    _emit(
        {
            "status": "training",
            "job_id": job_id,
            "preset": preset_id,
            "steps": 0,
            "max_steps": 6 if mode == "mesh" else 5,
            "loss": None,
            "psnr": None,
            "message": f"Старт AliceVision ({mode})…",
            "error": None,
            "vram_total_gb": round(total_vram_gb(), 2),
            "vram_used_gb": round(used_vram_gb(), 2),
        }
    )
    runtime_write("info", "recon_train", f"start alicevision mode={mode} job={job_id}")
    step_i = 0

    def emit_av(ev: dict[str, Any]) -> None:
        nonlocal step_i
        if ev.get("event") == "alicevision-step-done":
            step_i += 1
            ev = {**ev, "steps": step_i}
        _emit(ev)

    try:
        result = run_dense_pipeline(job_dir, mode=mode, emit=emit_av)
        man = _read_manifest(job_dir)
        man = patch_manifest_artifacts(man, job_dir, result)
        _write_manifest(job_dir, man)
        if result.get("ok"):
            art = man.get("artifact")
            _emit(
                {
                    "status": "done",
                    "artifact": art,
                    "steps": step_i or 1,
                    "max_steps": step_i or 1,
                    "message": f"Готово · {art}",
                    "error": None,
                    "eta_seconds": 0,
                }
            )
            runtime_write("info", "recon_train", f"done alicevision job={job_id} artifact={art}")
            return
        err = result.get("error") or result.get("warning") or "AliceVision не создал артефакты"
        # Preserve sparse — surface as soft error on train channel
        _emit({"status": "error", "error": err, "message": f"AliceVision: {err}"})
        runtime_write("warn", "recon_train", f"alicevision soft-fail job={job_id}: {err}")
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        man = _read_manifest(job_dir)
        man["alicevision_warning"] = err
        _write_manifest(job_dir, man)
        _emit({"status": "error", "error": err, "message": f"AliceVision: {err}"})
        runtime_write("error", "recon_train", f"alicevision exception job={job_id}: {err}")


def _run_da3_worker(job_id: str, preset_id: str, cfg: dict[str, Any]) -> None:
    """Dense point cloud via Depth Anything 3 (DA3); never wipe COLMAP sparse on failure."""
    job_dir = _job_dir(job_id)
    variant = str(cfg.get("variant") or "base")
    _emit(
        {
            "status": "training",
            "job_id": job_id,
            "preset": preset_id,
            "steps": 0,
            "max_steps": 2,
            "loss": None,
            "psnr": None,
            "message": f"Старт DA3 Dense ({variant})…",
            "error": None,
            "vram_total_gb": round(total_vram_gb(), 2),
            "vram_used_gb": round(used_vram_gb(), 2),
        }
    )
    runtime_write("info", "recon_train", f"start da3_dense variant={variant} job={job_id}")

    def emit_da3(ev: dict[str, Any]) -> None:
        stage = ev.get("stage")
        step = 1 if stage == "da3_depth" else (2 if stage in ("da3_fusion", "da3_done") else 0)
        _emit({**ev, "steps": step, "max_steps": 2})
        recon_scanner.emit_recon_event(ev)

    try:
        from services.da3_pipeline import DA3WeightsNotFoundError, run_da3_pipeline

        result = run_da3_pipeline(job_dir, variant=variant, emit=emit_da3)
        if result.get("ok"):
            _emit(
                {
                    "status": "done",
                    "artifact": result.get("dense_ply") or "dense.ply",
                    "steps": 2,
                    "max_steps": 2,
                    "message": f"Готово · dense.ply (DA3 {variant})",
                    "error": None,
                    "eta_seconds": 0,
                }
            )
            runtime_write("info", "recon_train", f"done da3_dense job={job_id} artifact=dense.ply")
            return

        err = result.get("error") or result.get("warning") or "DA3 не создал dense.ply"
        _emit({"status": "error", "error": err, "message": f"DA3: {err}"})
        runtime_write("warn", "recon_train", f"da3_dense soft-fail job={job_id}: {err}")
    except Exception as exc:  # noqa: BLE001
        from services.da3_pipeline import DA3WeightsNotFoundError

        err = str(exc)
        if isinstance(exc, DA3WeightsNotFoundError) or "DA3_WEIGHTS_NOT_FOUND" in err:
            err = "DA3_WEIGHTS_NOT_FOUND"
        _emit({"status": "error", "error": err, "message": f"DA3: {err}"})
        runtime_write("error", "recon_train", f"da3_dense exception job={job_id}: {err}")


def _run_worker(job_id: str, preset_id: str, cfg: dict[str, Any]) -> None:
    global _proc
    job_dir = _job_dir(job_id)
    py = str(PY if PY.is_file() else Path(__import__("sys").executable))
    script = str(cfg.get("script") or "gsplat")
    if script == "colmap_only":
        _run_sparse_select_worker(job_id, preset_id)
        return
    if script in _AV_SCRIPTS:
        _run_alicevision_worker(job_id, preset_id, cfg)
        return
    if script == "da3_dense":
        _run_da3_worker(job_id, preset_id, cfg)
        return
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
            "message": f"Старт {preset_id}… подготовка MSVC / данные",
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
        _emit({"message": "Патч JIT / проверка MSVC…"})
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
        _emit({"message": "Запуск gsplat (первый шаг может ждать CUDA JIT 1–3 мин)…"})

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
            last_heartbeat = t0
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
                now = time.time()
                if max_steps > 0 and _state.get("steps"):
                    steps = int(_state["steps"] or 0)
                    elapsed = max(1.0, now - t0)
                    rate = steps / elapsed
                    if rate > 0:
                        _emit({"eta_seconds": int(max(0, (max_steps - steps) / rate))})
                elif now - last_heartbeat >= 15.0 and int(_state.get("steps") or 0) == 0:
                    # Silent MSVC/data/JIT phase — keep UI from looking frozen at 0/N.
                    waited = int(now - t0)
                    _emit(
                        {
                            "message": (
                                f"Подготовка / CUDA JIT… {waited}с без шагов "
                                "(это нормально до первого it/s)"
                            )
                        }
                    )
                    last_heartbeat = now
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
    man_st = str(man.get("status") or "")
    if man_st == "running":
        raise RuntimeError("Дождитесь завершения COLMAP")

    # Detach hung/orphan scanner (e.g. mapper still in subprocess.run while disk is error)
    # so a finished job can train. Only block when COLMAP is running for THIS job.
    scan = recon_scanner.force_release_for_train(job_id)
    if (
        scan.get("status") == "running"
        and str(scan.get("job_id") or "") == job_id
    ):
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
    if script in _AV_SCRIPTS:
        import os

        from services.db import get_setting

        if script == "alicevision_mvs" and (os.environ.get("MURAVEI_LEGACY_AV_DENSE") or "").strip() != "1":
            raise RuntimeError(
                "AliceVision Dense (MVS) отключён по умолчанию. "
                "Установите MURAVEI_LEGACY_AV_DENSE=1 или используйте DA3 Dense / Mesh."
            )
        if (get_setting("alicevision_enabled") or "1") != "1":
            raise RuntimeError("AliceVision отключён инженером")
        if not alicevision_available():
            raise RuntimeError("AliceVision не установлен (sidecar / ALICEVISION_ROOT)")
        cuda_ok, cuda_reason = alicevision_cuda_ready()
        if not cuda_ok:
            raise RuntimeError(cuda_reason or "AliceVision требует CUDA")
    if script == "da3_dense":
        from fastapi import HTTPException
        from services.da3_pipeline import find_da3_weights

        variant = str(cfg.get("variant") or "base")
        w_path = find_da3_weights(variant)
        if not w_path:
            raise HTTPException(
                status_code=503,
                detail=f"DA3_WEIGHTS_NOT_FOUND: Веса модели DA3 ({variant}) не найдены в sidecars/da3/",
            )
    min_v = float(cfg.get("min_vram_gb") or 0)
    vram = total_vram_gb()
    if min_v and (vram <= 0 or vram < min_v):
        raise RuntimeError(
            f"Пресет {preset} требует ≥{min_v:g} ГБ VRAM (сейчас {vram:.1f} ГБ)"
        )

    with _lock:
        _recover_stale_training_unlocked()
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
