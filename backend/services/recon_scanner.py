"""Background 3D reconstruction job: frames → COLMAP → optional gsplat → manifest."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from services.colmap_poses import export_camera_poses, export_sparse_points, nearest_pose
from services.ffmpeg_util import video_duration_sec
from services.job_ids import sanitize_job_id
from services.recon_colmap import (
    choose_matcher,
    clamp_fps_sample,
    colmap_stage_progress,
    count_registered_images,
    feature_extractor_args,
    format_colmap_error,
    format_colmap_stage_message,
    mapper_progress_from_snapshot,
    matcher_cli_args,
    max_frames,
    max_image_size,
    registration_failure_message,
    sequential_overlap,
    sparse_mapper_snapshot,
)
from services.recon_diagnose import get_best_sparse_dir
from services.security import archive_root, assert_in_archive

BASE_DIR = Path(__file__).resolve().parents[2]
RECON_ROOT = BASE_DIR / "archive" / "recon"
LOG_PATH = BASE_DIR / "logs" / "recon.log"

MAX_SEGMENT_SEC = 120.0

_lock = threading.Lock()

# P0-7: Heartbeat interval for stale state detection (seconds)
HEARTBEAT_STALE_THRESHOLD = 300.0  # 5 minutes — COLMAP mapper can be slow

_state: dict[str, Any] = {
    "status": "idle",
    "job_id": None,
    "message": "",
    "video_path": None,
    "source_video": None,
    "phase": None,
    "stage": None,
    "progress": 0.0,
    "t_start": 0.0,
    "t_end": 0.0,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "_heartbeat": 0.0,  # P0-7: last activity timestamp
}
_events: list[dict[str, Any]] = []
_stop = threading.Event()
_thread: threading.Thread | None = None

def _log(msg: str) -> None:
    from services import runtime_log
    from services.trace_middleware import pipeline_trace

    runtime_log.info("recon", msg)
    # KEEP: session trace — do not remove without explicit user order
    pipeline_trace("recon", msg)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line)

def _emit(event: dict[str, Any]) -> None:
    with _lock:
        # Always attach live job_id so SSE clients never stick to a stale manifest id
        if "job_id" not in event and _state.get("job_id"):
            event = {**event, "job_id": _state["job_id"]}
        payload = {"ts": time.time(), **event}
        _events.append(payload)
        if len(_events) > 800:
            del _events[:400]
        for k, v in event.items():
            if k in _state:
                _state[k] = v
        if "status" in event:
            _state["status"] = event["status"]
        if "message" in event:
            _state["message"] = event["message"]
        if "error" in event:
            _state["error"] = event["error"]
        # P0-7: Update heartbeat on every event
        _state["_heartbeat"] = time.time()


def emit_recon_event(event: dict[str, Any]) -> None:
    """Public helper to push external pipeline events into recon stream."""
    _emit(event)


def _recover_stale_running_unlocked() -> bool:
    """If status is running but worker is dead OR disk job already terminal, reset to idle.

    Caller holds _lock. Disk may already be error/colmap_done after salvage while the
    Python thread is still blocked inside subprocess.run(COLMAP mapper) — that must
    not keep blocking gsplat train on a different finished job.
    """
    global _thread
    alive = bool(_thread and _thread.is_alive())
    if _state.get("status") != "running":
        return False

    from services.trace_middleware import pipeline_trace

    job_id = str(_state.get("job_id") or "")
    disk_st = ""
    disk_terminal = False
    if job_id:
        man = _read_manifest(RECON_ROOT / sanitize_job_id(job_id))
        disk_st = str(man.get("status") or "") if man else ""
        disk_terminal = bool(disk_st) and disk_st != "running"

    if alive and not disk_terminal:
        return False

    reason = "dead thread" if not alive else f"disk already {disk_st or '?'}"
    pipeline_trace(
        "recon",
        f"stale running recovered ({reason}) job={job_id or '?'}",
        level="warn",
    )
    if job_id and not disk_terminal:
        _finalize_dead_job_on_disk(job_id)
    if alive:
        _stop.set()
        # Prefer per-job PID terminate (terminate_colmap_for_job) after unlock —
        # never taskkill /IM colmap.exe (shared console CTRL-break risk).
    _state["status"] = "idle"
    _state["message"] = ""
    _state["error"] = None
    _state["phase"] = None
    _state["stage"] = None
    _state["progress"] = 0.0
    if not alive:
        _thread = None
    # Stash for callers / status() to reap orphan mapper outside the lock
    if job_id:
        _state["_reap_colmap_job"] = job_id
    return True

def terminate_colmap_for_job(job_id: str) -> int:
    """Terminate colmap processes whose cmdline references this job's colmap dir.

    Uses per-PID terminate (not taskkill /IM) so a shared console is not CTRL-broken.
    """
    job_id = sanitize_job_id(job_id)
    if not job_id:
        return 0
    needle = str((RECON_ROOT / job_id / "colmap").resolve()).lower().replace("\\", "/")
    killed = 0
    try:
        import psutil
    except ImportError:
        return 0
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = (proc.info.get("name") or "").lower()
            cmd_list = proc.info.get("cmdline") or []
            cmd = " ".join(str(x) for x in cmd_list).lower().replace("\\", "/")
            if "colmap" not in name and "colmap" not in cmd:
                continue
            if needle not in cmd:
                continue
            for child in proc.children(recursive=True):
                try:
                    child.terminate()
                except psutil.Error:
                    pass
            proc.terminate()
            killed += 1
            _log(f"terminated orphan colmap pid={proc.pid} job={job_id}")
        except (psutil.Error, TypeError, ValueError):
            continue
    return killed

def force_release_for_train(target_job_id: str) -> dict[str, Any]:
    """Ensure scanner does not block train on a finished job (cross-job hung COLMAP)."""
    target_job_id = sanitize_job_id(target_job_id)
    with _lock:
        _recover_stale_running_unlocked()
        st = dict(_state)
    if st.get("status") != "running":
        reap = str(st.get("_reap_colmap_job") or "")
        if reap and reap != target_job_id:
            terminate_colmap_for_job(reap)
            with _lock:
                _state.pop("_reap_colmap_job", None)
        return status()
    scan_job = str(st.get("job_id") or "")
    if scan_job and scan_job == target_job_id:
        return status()
    # Another job still flagged running — detach so train on target can proceed
    released_job = ""
    with _lock:
        if _recover_stale_running_unlocked():
            released_job = str(_state.pop("_reap_colmap_job", None) or scan_job)
        elif str(_state.get("job_id") or "") != target_job_id and _state.get("status") == "running":
            from services.trace_middleware import pipeline_trace

            released_job = str(_state.get("job_id") or "")
            pipeline_trace(
                "recon",
                f"release scanner busy job={released_job} for train job={target_job_id}",
                level="warn",
            )
            _stop.set()
            _state["status"] = "idle"
            _state["message"] = ""
            _state["error"] = None
            _state["phase"] = None
            _state["stage"] = None
            _state["progress"] = 0.0
            _state.pop("_reap_colmap_job", None)
    if released_job and released_job != target_job_id:
        terminate_colmap_for_job(released_job)
    return status()

def _finalize_dead_job_on_disk(job_id: str) -> None:
    """Mark orphaned running manifest as colmap_done (if sparse points exist) or error."""
    job_dir = RECON_ROOT / sanitize_job_id(job_id)
    man = _read_manifest(job_dir)
    if not man or str(man.get("status") or "") != "running":
        return
    sparse_model = get_best_sparse_dir(job_dir)
    sparse_path = job_dir / str(man.get("sparse_file") or "sparse_points.json")
    try:
        if sparse_model is not None:
            has_bin = (sparse_model / "points3D.bin").is_file()
            has_txt = (sparse_model / "points3D.txt").is_file()
            if has_bin and not has_txt:
                from services import runtime_log

                colmap = _colmap_bin()
                if colmap:
                    runtime_log.logged_run(
                        [
                            colmap,
                            "model_converter",
                            "--input_path",
                            str(sparse_model),
                            "--output_path",
                            str(sparse_model),
                            "--output_type",
                            "TXT",
                        ],
                        "recon",
                        timeout=600,
                    )
                    has_txt = (sparse_model / "points3D.txt").is_file()
            if has_txt or (sparse_model / "points3D.txt").is_file():
                n = export_sparse_points(sparse_model, sparse_path)
                if n > 0:
                    man["status"] = "colmap_done"
                    man["error"] = None
                    man["finished_at"] = time.time()
                    man["next_action"] = "balanced_for_splat"
                    _write_manifest(job_dir, man)
                    _log(
                        f"salvaged dead job={job_id} → colmap_done "
                        f"sparse={n} model={sparse_model.name}"
                    )
                    return
    except Exception as exc:  # noqa: BLE001
        _log(f"salvage failed job={job_id}: {exc}")
    man["status"] = "error"
    man["error"] = "COLMAP worker died (stale running)"
    man["finished_at"] = time.time()
    _write_manifest(job_dir, man)
    _log(f"marked dead job={job_id} status=error")

def _scrub_orphan_running_manifests() -> None:
    """Disk manifests stuck at running with no live worker → finalize."""
    if not RECON_ROOT.is_dir():
        return
    live_id = ""
    with _lock:
        # Protect the job of any alive worker even if _state was detached to idle
        # (recover/force_release) — otherwise scrub falsely marks it error mid-COLMAP.
        if _thread and _thread.is_alive():
            live_id = str(_state.get("job_id") or "")
    for child in RECON_ROOT.iterdir():
        if not child.is_dir():
            continue
        man = _read_manifest(child)
        if not man or str(man.get("status") or "") != "running":
            continue
        jid = str(man.get("job_id") or child.name)
        if jid and live_id and jid == live_id:
            continue
        if not live_id and _thread and _thread.is_alive():
            # Alive worker but job_id cleared — do not scrub any running job this pass
            return
        _finalize_dead_job_on_disk(jid)

def status() -> dict[str, Any]:
    with _lock:
        _recover_stale_running_unlocked()
        # P0-7: Check heartbeat staleness
        _check_heartbeat_stale()
        reap = str(_state.pop("_reap_colmap_job", None) or "")
    if reap:
        terminate_colmap_for_job(reap)
    _scrub_orphan_running_manifests()
    with _lock:
        out = dict(_state)
        out.pop("_reap_colmap_job", None)
        return out


def _check_heartbeat_stale() -> bool:
    """Check if heartbeat is stale and recover if needed.

    P0-7: If status is running but no heartbeat for HEARTBEAT_STALE_THRESHOLD
    seconds, the worker thread is likely dead or hung.

    Returns:
        True if stale heartbeat was detected and recovered
    """
    if _state.get("status") != "running":
        return False

    heartbeat = float(_state.get("_heartbeat") or 0)
    if heartbeat == 0:
        # No heartbeat yet — thread just started, give it time
        return False

    age = time.time() - heartbeat
    if age > HEARTBEAT_STALE_THRESHOLD:
        _log(
            f"P0-7: Stale heartbeat detected (age={age:.0f}s > "
            f"{HEARTBEAT_STALE_THRESHOLD}s threshold), recovering"
        )
        return _recover_stale_running_unlocked()
    return False

def drain_events(after_idx: int = 0) -> tuple[list[dict[str, Any]], int]:
    with _lock:
        chunk = _events[after_idx:]
        return chunk, len(_events)

def _canonical_source(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(archive_root().resolve())
        return f"archive/{rel.as_posix()}"
    except Exception:
        return str(path)

def _resolve_video(video_path: str) -> tuple[Path, str]:
    raw = (video_path or "").strip()
    if not raw:
        raise ValueError("video_path пуст")
    p = Path(raw)
    if not p.is_absolute():
        cand = (
            BASE_DIR / raw
            if raw.replace("\\", "/").startswith("archive/")
            else archive_root() / raw
        )
        p = cand
    target = assert_in_archive(p)
    if not target.is_file():
        raise FileNotFoundError(f"Видео не найдено: {target}")
    if target.suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        raise ValueError(f"Неподдерживаемый формат: {target.suffix}")
    source_key = _canonical_source(target)
    return target, source_key

def _colmap_candidates(root: Path) -> list[Path]:
    names = (
        "COLMAP.bat",
        "colmap.exe",
        "colmap",
        Path("bin") / "colmap.exe",
    )
    out: list[Path] = []
    for name in names:
        cand = root / name
        if cand.is_file():
            out.append(cand)
    return out

def _colmap_bin() -> str | None:
    roots: list[Path] = []
    env_root = os.environ.get("COLMAP_ROOT", "").strip()
    if env_root:
        roots.append(Path(env_root))
    sidecar = BASE_DIR / "sidecars" / "colmap"
    if sidecar not in roots:
        roots.append(sidecar)
    for root in roots:
        cands = _colmap_candidates(root)
        if cands:
            chosen = str(cands[0])
            if not env_root and root == sidecar:
                _log(f"COLMAP auto-detected: {chosen}")
            return chosen
    found = shutil.which("colmap")
    return found

def colmap_available() -> bool:
    return _colmap_bin() is not None

def colmap_path() -> str | None:
    return _colmap_bin()

def _job_dir(job_id: str) -> Path:
    return RECON_ROOT / sanitize_job_id(job_id)

def _write_manifest(job_dir: Path, data: dict[str, Any]) -> None:
    path = job_dir / "manifest.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _read_manifest(job_dir: Path) -> dict[str, Any] | None:
    path = job_dir / "manifest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

def _video_path_matches(manifest_path: str, key: str) -> bool:
    vp = manifest_path.replace("\\", "/")
    k = key.replace("\\", "/")
    if vp == k:
        return True
    base = k.split("/")[-1]
    if base and vp.endswith("/" + base):
        return True
    if base and vp.split("/")[-1] == base:
        return True
    return False

def _manifest_rank(man: dict[str, Any]) -> tuple[int, float]:
    st = str(man.get("status") or "")
    artifact = str(man.get("artifact") or "").strip()
    # Prefer photoreal splat (done + artifact) over newer sparse-only colmap_done
    if st == "done" and artifact:
        pri = 4
    elif st in ("colmap_done", "done"):
        pri = 3
    elif st == "running":
        pri = 1
    else:
        pri = 0
    return pri, float(man.get("created_at") or 0)

def find_latest_job_for_video(source_video: str) -> dict[str, Any] | None:
    """Return best recon job for this video — prefer colmap_done/done over running."""
    if not RECON_ROOT.is_dir():
        return None
    key = source_video.replace("\\", "/")
    matches: list[dict[str, Any]] = []
    for child in RECON_ROOT.iterdir():
        if not child.is_dir():
            continue
        man = _read_manifest(child)
        if not man:
            continue
        vp = str(man.get("video_path") or "")
        if not _video_path_matches(vp, key):
            continue
        matches.append(man)
    if not matches:
        return None
    return max(matches, key=_manifest_rank)

def _extract_frames(
    video: Path,
    frames_dir: Path,
    t_start: float,
    t_end: float,
    fps_sample: float,
    *,
    source_video: str | None = None,
) -> tuple[dict[str, float], int, dict[str, float] | None]:
    import cv2

    from services.hud_exclusion import (
        archive_hud_enabled,
        crop_frame,
        ensure_zones_async,
        get_zones,
    )

    frames_dir.mkdir(parents=True, exist_ok=True)
    hud_crop: dict[str, float] | None = None
    zones = None
    if source_video and archive_hud_enabled():
        ensure_zones_async(source_video)
        z = get_zones(source_video, kickoff=True, wait=False)
        if z.has_exclusion():
            zones = z
            hud_crop = {
                "top": z.top,
                "bottom": z.bottom,
                "left": z.left,
                "right": z.right,
            }

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Не удалось открыть видео: {video.name}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0) or 25.0
    sample = clamp_fps_sample(t_start, t_end, max(0.1, float(fps_sample)))
    step_sec = 1.0 / sample
    frame_budget = max_frames()
    img_cap = max_image_size()
    frame_times: dict[str, float] = {}
    count = 0
    t = float(t_start)
    full_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    full_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    while t <= t_end + 1e-6 and count < frame_budget:
        if _stop.is_set():
            cap.release()
            raise RuntimeError("Остановлено оператором")
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            t += step_sec
            continue
        if full_w <= 0 or full_h <= 0:
            full_h, full_w = frame.shape[:2]
        if zones is not None:
            frame, _ = crop_frame(frame, zones)
        # Cap longest side before COLMAP (8 GB VRAM safety; relative limit)
        h, w = frame.shape[:2]
        long_side = max(h, w)
        if long_side > img_cap:
            scale = img_cap / float(long_side)
            frame = cv2.resize(
                frame,
                (max(1, int(w * scale)), max(1, int(h * scale))),
                interpolation=cv2.INTER_AREA,
            )
        count += 1
        name = f"{count:06d}.jpg"
        out = frames_dir / name
        cv2.imwrite(str(out), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        frame_times[name] = round(t, 4)
        t += step_sec
    cap.release()
    if count < 3:
        raise RuntimeError(f"Слишком мало кадров ({count}). Нужно ≥3 для COLMAP.")
    if hud_crop is not None:
        hud_crop = {**hud_crop, "full_width": full_w, "full_height": full_h}
    return frame_times, count, hud_crop

def _run_colmap(job_dir: Path, frames_dir: Path) -> Path:
    colmap = _colmap_bin()
    if not colmap:
        raise RuntimeError(
            "COLMAP не найден. Установите sidecar и задайте COLMAP_ROOT "
            "(см. docs/RECON_3D.md)."
        )
    colmap_ws = job_dir / "colmap"
    db = colmap_ws / "database.db"
    sparse = colmap_ws / "sparse"
    colmap_ws.mkdir(parents=True, exist_ok=True)
    sparse.mkdir(parents=True, exist_ok=True)

    n_frames = sum(1 for p in frames_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    matcher = choose_matcher(n_frames, source="video")
    overlap = sequential_overlap()
    img_size = max_image_size()
    matcher_stage = f"{matcher}_matcher"
    _log(
        f"COLMAP plan frames={n_frames} matcher={matcher} "
        f"overlap={overlap} max_image_size={img_size}"
    )
    _emit(
        {
            "status": "running",
            "phase": "colmap",
            "stage": "plan",
            "progress": colmap_stage_progress("plan"),
            "message": format_colmap_stage_message(
                "plan", n_frames=n_frames, matcher=matcher
            ),
        }
    )

    def emit_stage(stage: str, *, snap: dict[str, Any] | None = None) -> None:
        prog = (
            mapper_progress_from_snapshot(snap)
            if stage == "mapper"
            else colmap_stage_progress(stage)
        )
        _emit(
            {
                "status": "running",
                "phase": "colmap",
                "stage": stage,
                "progress": prog,
                "message": format_colmap_stage_message(
                    stage, n_frames=n_frames, matcher=matcher, snap=snap
                ),
            }
        )

    def run(args: list[str], timeout: int = 3600, *, stage: str = "") -> None:
        from services import runtime_log

        cmd = [colmap, *args]
        proc = runtime_log.logged_run(cmd, "recon", timeout=timeout)
        if proc.returncode != 0:
            combined = (proc.stderr or "") + "\n" + (proc.stdout or "")
            raise RuntimeError(
                format_colmap_error(proc.returncode, combined, stage=stage or args[0])
            )

    def run_mapper_with_poll(timeout: int = 7200, *, poll_sec: float = 5.0) -> None:
        """Long mapper: Popen + sparse/N snapshot emits (real artifacts, not fake %)."""
        from services import runtime_log

        args = [
            "mapper",
            "--database_path",
            str(db),
            "--image_path",
            str(frames_dir),
            "--output_path",
            str(sparse),
        ]
        cmd = [colmap, *args]
        emit_stage("mapper")
        runtime_log.cmd("recon", cmd)
        # Capture to temp so pipe buffer never blocks COLMAP glog spam
        log_path = colmap_ws / "mapper_live.log"
        started = time.time()
        last_emit_key: tuple[Any, ...] | None = None
        with log_path.open("w", encoding="utf-8", errors="replace") as logf:
            proc = subprocess.Popen(
                cmd,
                stdout=logf,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                while True:
                    rc = proc.poll()
                    if rc is not None:
                        break
                    if _stop.is_set():
                        proc.terminate()
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                        raise RuntimeError("COLMAP mapper остановлен")
                    if time.time() - started > timeout:
                        proc.kill()
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            pass
                        raise RuntimeError(
                            format_colmap_error(-1, "mapper timeout", stage="mapper")
                        )
                    snap = sparse_mapper_snapshot(sparse)
                    # Emit when models change, or every poll with age bucket (10s) so UI stays live
                    age = snap.get("last_write_age_sec")
                    age_bucket = None if age is None else int(age) // 10
                    key = (snap.get("model_count"), snap.get("last_model"), age_bucket)
                    if key != last_emit_key:
                        last_emit_key = key
                        emit_stage("mapper", snap=snap)
                    time.sleep(poll_sec)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass

        combined = ""
        try:
            combined = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            combined = ""
        if proc.returncode != 0:
            if combined:
                from services import runtime_log as rl

                for line in combined.splitlines()[:8]:
                    rl.write("warn", "recon", line, kind="stderr")
                rl.warn("recon", f"exit code {proc.returncode}")
            raise RuntimeError(
                format_colmap_error(proc.returncode or 1, combined, stage="mapper")
            )
        from services import runtime_log as rl

        rl.debug("recon", "exit 0")

    from services.accelerator import colmap_use_gpu, is_cpu_profile, log_profile_once

    log_profile_once()
    sift_gpu = colmap_use_gpu()
    if is_cpu_profile():
        _log(
            f"CPU-профиль COLMAP: use_gpu=0 max_image_size={img_size} "
            f"frames≈{n_frames} (ETA: десятки минут–часы на длинном клипе)"
        )

    emit_stage("feature_extractor")
    run(
        feature_extractor_args(db, frames_dir, use_gpu=sift_gpu, image_size=img_size),
        stage="feature_extractor",
    )

    def run_matcher(*, use_gpu: bool) -> None:
        emit_stage(matcher_stage)
        run(
            matcher_cli_args(matcher, db, overlap=overlap, use_gpu=use_gpu),
            stage=matcher_stage,
        )

    try:
        run_matcher(use_gpu=sift_gpu)
    except RuntimeError as gpu_exc:
        from services.trace_middleware import pipeline_trace

        if not sift_gpu:
            raise
        msg = (
            f"GPU matching failed — retry once with CPU "
            f"({matcher}, frames={n_frames}): {gpu_exc}"
        )
        _log(msg)
        pipeline_trace("recon", msg, level="warn")
        run_matcher(use_gpu=False)

    # COLMAP mapper writes sparse/0, sparse/1, … under --output_path.
    run_mapper_with_poll(timeout=7200)

    sparse_model = get_best_sparse_dir(job_dir)
    if sparse_model is None:
        raise RuntimeError("COLMAP mapper produced no valid sparse model")

    need_txt = not (sparse_model / "cameras.txt").is_file() or (
        not (sparse_model / "points3D.txt").is_file()
        and (sparse_model / "points3D.bin").is_file()
    )
    if need_txt:
        emit_stage("model_converter")
        run(
            [
                "model_converter",
                "--input_path",
                str(sparse_model),
                "--output_path",
                str(sparse_model),
                "--output_type",
                "TXT",
            ],
            stage="model_converter",
        )

    n_reg = count_registered_images(sparse_model)
    weak = registration_failure_message(n_frames, n_reg)
    if weak:
        raise RuntimeError(weak)
    return sparse_model

def _try_salvage_after_error(job_dir: Path, manifest: dict[str, Any]) -> bool:
    """If mapper left a usable sparse model, promote to colmap_done instead of error."""
    sparse_model = get_best_sparse_dir(job_dir)
    if sparse_model is None:
        return False
    sparse_path = job_dir / str(manifest.get("sparse_file") or "sparse_points.json")
    try:
        if not (sparse_model / "points3D.txt").is_file() and (sparse_model / "points3D.bin").is_file():
            colmap = _colmap_bin()
            if colmap:
                from services import runtime_log

                runtime_log.logged_run(
                    [
                        colmap,
                        "model_converter",
                        "--input_path",
                        str(sparse_model),
                        "--output_path",
                        str(sparse_model),
                        "--output_type",
                        "TXT",
                    ],
                    "recon",
                    timeout=600,
                )
        if not (sparse_model / "points3D.txt").is_file():
            return False
        n = export_sparse_points(sparse_model, sparse_path)
        if n <= 0:
            return False
        poses_path = job_dir / str(manifest.get("poses_file") or "camera_poses.json")
        if not poses_path.is_file():
            export_camera_poses(
                sparse_model,
                poses_path,
                frame_times={},
                t_start=float(manifest.get("t_start") or 0.0),
                fps_sample=float(manifest.get("fps_sample") or 1.0),
            )
        manifest["status"] = "colmap_done"
        manifest["error"] = None
        manifest["finished_at"] = time.time()
        manifest["next_action"] = "balanced_for_splat"
        _write_manifest(job_dir, manifest)
        _log(f"salvaged after error → colmap_done sparse={n} job={manifest.get('job_id')}")
        return True
    except Exception as exc:  # noqa: BLE001
        _log(f"post-error salvage failed: {exc}")
        return False

def _try_gsplat_train(job_dir: Path, frames_dir: Path, sparse0: Path) -> str | None:
    """Optional gsplat train → model.ply / preview.ply. Never fails the COLMAP job."""
    try:
        import torch  # noqa: PLC0415
    except ImportError:
        _log("torch not available — skip gsplat")
        return None
    if not torch.cuda.is_available():
        _log("CUDA unavailable — skip gsplat train")
        return None

    script = BASE_DIR / "backend" / "scripts" / "gsplat_train_job.py"
    if not script.is_file():
        _log("gsplat_train_job.py missing — skip")
        return None

    py = BASE_DIR / "muravei_env" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)

    max_steps = int(os.environ.get("GSPLAT_MAX_STEPS", "500"))
    cmd = [
        str(py),
        str(script),
        "--job-dir",
        str(job_dir),
        "--max-steps",
        str(max_steps),
    ]
    _log(f"gsplat train: {' '.join(cmd)}")
    try:
        from services import runtime_log

        proc = runtime_log.logged_run(cmd, "recon", timeout=int(os.environ.get("GSPLAT_TIMEOUT", "3600")))
    except Exception as exc:  # noqa: BLE001
        _log(f"gsplat train failed: {exc}")
        return None

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:400]
        _log(f"gsplat train exit {proc.returncode}: {err}")
        return None

    for name in ("model.ply", "preview.ply"):
        if (job_dir / name).is_file():
            _log(f"gsplat artifact: {name}")
            return name
    _log("gsplat train OK but no ply artifact")
    return None

def _run(
    job_id: str,
    video_abs: Path,
    source_video: str,
    t_start: float,
    t_end: float,
    fps_sample: float,
) -> None:
    """Main recon worker thread target (P1-13: proper exception handling)."""
    global _thread
    job_dir = _job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = job_dir / "frames"
    manifest: dict[str, Any] = {
        "job_id": job_id,
        "video_path": source_video,
        "t_start": t_start,
        "t_end": t_end,
        "fps_sample": fps_sample,
        "status": "running",
        "artifact": None,
        "poses_file": "camera_poses.json",
        "sparse_file": "sparse_points.json",
        "scale_m_per_unit": None,
        "scale_reference": None,
        "rotation_x": 0.0,
        "created_at": time.time(),
    }
    _write_manifest(job_dir, manifest)

    try:
        _emit(
            {
                "status": "running",
                "job_id": job_id,
                "phase": "extracting",
                "stage": "extract_frames",
                "progress": 0.05,
                "message": "Извлечение кадров…",
                "video_path": str(video_abs),
                "source_video": source_video,
                "t_start": t_start,
                "t_end": t_end,
                "error": None,
            }
        )
        frame_times, n_frames, hud_crop = _extract_frames(
            video_abs, frames_dir, t_start, t_end, fps_sample, source_video=source_video
        )
        _log(f"extracted {n_frames} frames → {frames_dir}")
        if hud_crop:
            _log(
                f"HUD crop t={hud_crop.get('top')} b={hud_crop.get('bottom')} "
                f"l={hud_crop.get('left')} r={hud_crop.get('right')}"
            )

        sparse0 = _run_colmap(job_dir, frames_dir)

        _emit(
            {
                "status": "running",
                "phase": "export_poses",
                "stage": "export_poses",
                "progress": 0.65,
                "message": "Экспорт camera poses…",
            }
        )
        poses_path = job_dir / "camera_poses.json"
        export_camera_poses(
            sparse0,
            poses_path,
            frame_times=frame_times,
            t_start=t_start,
            fps_sample=fps_sample,
            hud_crop=hud_crop,
        )
        sparse_path = job_dir / "sparse_points.json"
        n_sparse = export_sparse_points(sparse0, sparse_path)
        _log(f"sparse points exported: {n_sparse}")

        # Default: Build3D = COLMAP sparse only. Photoreal via UI Balanced/Bootstrap/High.
        # Opt-in short inline train: set GSPLAT_INLINE=1 (keeps _try_gsplat_train).
        artifact: str | None = None
        if os.environ.get("GSPLAT_INLINE") == "1":
            _emit(
                {
                    "status": "running",
                    "phase": "training",
                    "stage": "gsplat_inline",
                    "progress": 0.75,
                    "message": "gsplat train (optional)…",
                }
            )
            artifact = _try_gsplat_train(job_dir, frames_dir, sparse0)
        else:
            _log("inline gsplat skipped (use UI Balanced); set GSPLAT_INLINE=1 to enable")

        final_status = "colmap_done" if not artifact else "done"
        manifest.update(
            {
                "status": final_status,
                "artifact": artifact,
                "frame_count": n_frames,
                "finished_at": time.time(),
            }
        )
        if not artifact:
            manifest["next_action"] = "balanced_for_splat"
        else:
            manifest.pop("next_action", None)
        if hud_crop:
            manifest["hud_crop"] = {
                "top": hud_crop.get("top", 0),
                "bottom": hud_crop.get("bottom", 0),
                "left": hud_crop.get("left", 0),
                "right": hud_crop.get("right", 0),
            }
        _write_manifest(job_dir, manifest)

        _emit(
            {
                "status": final_status,
                "phase": final_status,
                "stage": "colmap_done" if not artifact else "done",
                "progress": 1.0,
                "message": (
                    "готово (sparse) · запустите Balanced для splat"
                    if not artifact
                    else f"3D готов: {artifact}"
                ),
                "finished_at": time.time(),
            }
        )
        _log(f"done job={job_id} status={final_status}")
    except Exception as exc:  # noqa: BLE001 — P1-13: catch all, salvage, cleanup
        _log(f"ERROR {exc}")
        if _try_salvage_after_error(job_dir, manifest):
            _emit(
                {
                    "status": "colmap_done",
                    "phase": "colmap_done",
                    "stage": "colmap_done",
                    "progress": 1.0,
                    "message": "готово (sparse, salvaged) · запустите Balanced для splat",
                    "error": None,
                    "finished_at": time.time(),
                }
            )
        else:
            err_msg = str(exc)
            # Never surface raw glog INFO dumps if something bypassed format_colmap_error
            if err_msg.startswith("COLMAP failed:") and "I20" in err_msg:
                err_msg = format_colmap_error(1, err_msg, stage="colmap")
            manifest["status"] = "error"
            manifest["error"] = err_msg
            manifest["finished_at"] = time.time()
            _write_manifest(job_dir, manifest)
            _emit(
                {
                    "status": "error",
                    "error": err_msg,
                    "message": err_msg,
                    "finished_at": time.time(),
                }
            )
    finally:
        # P1-13: Always cleanup thread reference, even on exception
        with _lock:
            _thread = None
            # KEEP: recover zombie — thread ended without final status
            if _state.get("status") == "running":
                _state["status"] = "error"
                _state["message"] = "Zombie job reset"
                _state["error"] = "Zombie job reset"
                _state["finished_at"] = time.time()
                _events.append(
                    {
                        "ts": time.time(),
                        "status": "error",
                        "message": "Zombie job reset",
                        "error": "Zombie job reset",
                    }
                )

def start(
    video_path: str,
    t_start: float | None = None,
    t_end: float | None = None,
    fps_sample: float = 1.0,
) -> dict[str, Any]:
    global _thread
    with _lock:
        _recover_stale_running_unlocked()
        alive = bool(_thread and _thread.is_alive())
        if _state["status"] == "running" or alive:
            raise RuntimeError("Реконструкция уже выполняется")
        video_abs, source_video = _resolve_video(video_path)
        dur = video_duration_sec(video_abs) or 0.0
        ts = max(0.0, float(t_start or 0.0))
        te = float(t_end if t_end is not None else min(dur, ts + 60.0))
        if te <= ts:
            te = ts + min(60.0, MAX_SEGMENT_SEC)
        if te - ts > MAX_SEGMENT_SEC:
            te = ts + MAX_SEGMENT_SEC
        if dur > 0:
            te = min(te, dur)

        fps = clamp_fps_sample(ts, te, float(fps_sample))
        if abs(fps - float(fps_sample)) > 1e-6:
            _log(
                f"fps_sample clamped {fps_sample} → {fps:.4f} "
                f"(segment={te - ts:.1f}s, max_frames={max_frames()})"
            )

        job_id = sanitize_job_id(uuid.uuid4().hex[:12])
        _stop.clear()
        _events.clear()
        _state.update(
            {
                "status": "running",
                "job_id": job_id,
                "message": "Запуск…",
                "video_path": str(video_abs),
                "source_video": source_video,
                "phase": "starting",
                "stage": None,
                "progress": 0.0,
                "t_start": ts,
                "t_end": te,
                "started_at": time.time(),
                "finished_at": None,
                "error": None,
            }
        )
        _thread = threading.Thread(
            target=_run,
            args=(job_id, video_abs, source_video, ts, te, fps),
            daemon=True,
            name="recon-scanner",
        )
        _thread.start()
    return status()

def stop() -> dict[str, Any]:
    _stop.set()
    _emit({"message": "Остановка реконструкции…"})
    return status()

def get_manifest(video_path: str) -> dict[str, Any] | None:
    _, source_video = _resolve_video(video_path)
    return find_latest_job_for_video(source_video)

def get_poses_at_time(video_path: str, time_sec: float) -> dict[str, Any] | None:
    man = get_manifest(video_path)
    if not man:
        return None
    t_start = float(man.get("t_start") or 0)
    t_end = float(man.get("t_end") or 0)
    if t_end > t_start and (time_sec < t_start - 0.5 or time_sec > t_end + 0.5):
        raise ValueError(
            f"Время {time_sec:.1f}s вне сегмента реконструкции "
            f"({t_start:.1f}–{t_end:.1f}s). Переместите playhead в сегмент "
            "или постройте 3D для нужного участка."
        )
    job_id = man.get("job_id")
    if not job_id:
        return None
    poses_path = _job_dir(str(job_id)) / "camera_poses.json"
    if not poses_path.is_file():
        return None
    doc = json.loads(poses_path.read_text(encoding="utf-8"))
    pose = nearest_pose(doc, float(time_sec))
    if not pose:
        return None
    return {"job_id": job_id, "time_sec": time_sec, "pose": pose, "manifest": man}

def update_manifest(job_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    job_id = sanitize_job_id(job_id)
    job_dir = _job_dir(job_id)
    if not job_dir.is_dir():
        raise FileNotFoundError(f"Job not found: {job_id}")
    man = _read_manifest(job_dir) or {"job_id": job_id}
    allowed = {
        "scale_m_per_unit",
        "scale_reference",
        "rotation_x",
    }
    for k, v in patch.items():
        if k in allowed:
            man[k] = v
    _write_manifest(job_dir, man)
    return man

def asset_path(job_id: str, name: str) -> Path:
    """Resolve asset path with strict path traversal protection.

    Uses pathlib.Path.relative_to() (not startswith) to prevent
    path traversal attacks like '../../../etc/passwd'.
    """
    job_dir = _job_dir(sanitize_job_id(job_id))
    resolved_job_dir = job_dir.resolve()
    target = (resolved_job_dir / name).resolve()
    # relative_to() raises ValueError if target is outside job_dir
    try:
        target.relative_to(resolved_job_dir)
    except ValueError:
        raise ValueError("Path traversal detected: asset outside job directory")
    if not target.is_file():
        raise FileNotFoundError(name)
    return target
