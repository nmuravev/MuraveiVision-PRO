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
from services.recon_diagnose import get_best_sparse_dir
from services.security import archive_root, assert_in_archive

BASE_DIR = Path(__file__).resolve().parents[2]
RECON_ROOT = BASE_DIR / "archive" / "recon"
LOG_PATH = BASE_DIR / "logs" / "recon.log"

MAX_SEGMENT_SEC = 120.0

_lock = threading.Lock()
_state: dict[str, Any] = {
    "status": "idle",
    "job_id": None,
    "message": "",
    "video_path": None,
    "source_video": None,
    "phase": None,
    "progress": 0.0,
    "t_start": 0.0,
    "t_end": 0.0,
    "started_at": None,
    "finished_at": None,
    "error": None,
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
    payload = {"ts": time.time(), **event}
    with _lock:
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


def _recover_stale_running_unlocked() -> bool:
    """If status is running but worker thread is dead, reset to idle. Caller holds _lock."""
    global _thread
    alive = bool(_thread and _thread.is_alive())
    if _state.get("status") == "running" and not alive:
        from services.trace_middleware import pipeline_trace

        pipeline_trace(
            "recon",
            "stale running recovered (dead thread)",
            level="warn",
        )
        _state["status"] = "idle"
        _state["message"] = ""
        _state["error"] = None
        _state["phase"] = None
        _state["progress"] = 0.0
        _thread = None
        return True
    return False


def status() -> dict[str, Any]:
    with _lock:
        _recover_stale_running_unlocked()
        return dict(_state)


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
    if st in ("colmap_done", "done"):
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
    sample = max(0.1, float(fps_sample))
    step_sec = 1.0 / sample
    frame_times: dict[str, float] = {}
    count = 0
    t = float(t_start)
    full_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    full_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    while t <= t_end + 1e-6:
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

    def run(args: list[str], timeout: int = 3600) -> None:
        from services import runtime_log

        cmd = [colmap, *args]
        proc = runtime_log.logged_run(cmd, "recon", timeout=timeout)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:800]
            raise RuntimeError(f"COLMAP failed: {err}")

    run(
        [
            "feature_extractor",
            "--database_path",
            str(db),
            "--image_path",
            str(frames_dir),
            "--ImageReader.single_camera",
            "1",
        ]
    )
    run(["exhaustive_matcher", "--database_path", str(db)])
    # COLMAP mapper writes sparse/0, sparse/1, … under --output_path.
    run(
        [
            "mapper",
            "--database_path",
            str(db),
            "--image_path",
            str(frames_dir),
            "--output_path",
            str(sparse),
        ],
        timeout=7200,
    )
    sparse_model = get_best_sparse_dir(job_dir)
    if sparse_model is None:
        raise RuntimeError("COLMAP mapper produced no valid sparse model")

    if not (sparse_model / "cameras.txt").is_file():
        run(
            [
                "model_converter",
                "--input_path",
                str(sparse_model),
                "--output_path",
                str(sparse_model),
                "--output_type",
                "TXT",
            ]
        )
    if not (sparse_model / "points3D.txt").is_file() and (sparse_model / "points3D.bin").is_file():
        run(
            [
                "model_converter",
                "--input_path",
                str(sparse_model),
                "--output_path",
                str(sparse_model),
                "--output_type",
                "TXT",
            ]
        )
    return sparse_model


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

        _emit({"status": "running", "phase": "colmap", "progress": 0.35, "message": "COLMAP feature extract + mapper…"})
        sparse0 = _run_colmap(job_dir, frames_dir)

        _emit({"status": "running", "phase": "export_poses", "progress": 0.65, "message": "Экспорт camera poses…"})
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
    except Exception as exc:  # noqa: BLE001
        _log(f"ERROR {exc}")
        manifest["status"] = "error"
        manifest["error"] = str(exc)
        manifest["finished_at"] = time.time()
        _write_manifest(job_dir, manifest)
        _emit(
            {
                "status": "error",
                "error": str(exc),
                "message": str(exc),
                "finished_at": time.time(),
            }
        )
    finally:
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
            args=(job_id, video_abs, source_video, ts, te, float(fps_sample)),
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
    job_dir = _job_dir(sanitize_job_id(job_id))
    target = (job_dir / name).resolve()
    if not str(target).startswith(str(job_dir.resolve())):
        raise ValueError("Invalid asset path")
    if not target.is_file():
        raise FileNotFoundError(name)
    return target
