"""COLMAP helpers for video SfM: matching strategy, frame budget, honest errors.

Zero absolute paths / job IDs — relative limits and env knobs only.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

# Defaults tuned for continuous drone video on ~8 GB VRAM edge laptops.
DEFAULT_SEQUENTIAL_OVERLAP = 15
DEFAULT_MAX_IMAGE_SIZE = 1600
DEFAULT_MAX_FRAMES = 600
DEFAULT_MIN_FRAMES_HINT = 200
DEFAULT_EXHAUSTIVE_MAX_IMAGES = 80
MIN_REGISTERED_ABS = 3
MIN_REGISTERED_RATIO = 0.25

_GLOG_INFO_RE = re.compile(r"^I\d{8}\b")
_GLOG_WARN_RE = re.compile(r"^W\d{8}\b")
_GLOG_ERR_RE = re.compile(r"^[EF]\d{8}\b")
_ERR_KW_RE = re.compile(
    r"error|fail|exception|crash|oom|out of memory|aborted|terminate|segfault",
    re.I,
)
_STRIP_GLOG_RE = re.compile(r"^[IWEF]\d{8}\s+\d+\s+[\w./\\-]+:\d+\]\s*")


def env_int(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
    except ValueError:
        return default
    return max(lo, min(hi, val))


def sequential_overlap() -> int:
    return env_int(
        "COLMAP_SEQUENTIAL_OVERLAP",
        DEFAULT_SEQUENTIAL_OVERLAP,
        lo=5,
        hi=40,
    )


def max_image_size() -> int:
    return env_int(
        "COLMAP_MAX_IMAGE_SIZE",
        DEFAULT_MAX_IMAGE_SIZE,
        lo=640,
        hi=3200,
    )


def max_frames() -> int:
    return env_int(
        "COLMAP_MAX_FRAMES",
        DEFAULT_MAX_FRAMES,
        lo=50,
        hi=2000,
    )


def exhaustive_max_images() -> int:
    return env_int(
        "COLMAP_EXHAUSTIVE_MAX_IMAGES",
        DEFAULT_EXHAUSTIVE_MAX_IMAGES,
        lo=20,
        hi=200,
    )


def clamp_fps_sample(
    t_start: float,
    t_end: float,
    fps_sample: float,
    *,
    max_n: int | None = None,
) -> float:
    """Reduce fps so expected frame count stays within budget for the segment."""
    duration = max(0.1, float(t_end) - float(t_start))
    requested = max(0.1, float(fps_sample))
    cap = int(max_n if max_n is not None else max_frames())
    expected = int(duration * requested) + 1
    if expected <= cap:
        return requested
    return max(0.1, (cap - 1) / duration)


def choose_matcher(n_frames: int, *, source: str = "video") -> str:
    """Return 'sequential' or 'exhaustive'.

    Video-derived frames always default to sequential. Exhaustive is opt-in via
    COLMAP_MATCHER=exhaustive and only allowed for small sets (< exhaustive_max).
    """
    forced = (os.environ.get("COLMAP_MATCHER") or "").strip().lower()
    n = max(0, int(n_frames))
    if forced == "sequential":
        return "sequential"
    if forced == "exhaustive":
        # Explicit opt-in — still refuse O(n²) on large sets
        return "exhaustive" if n <= exhaustive_max_images() else "sequential"
    # Default: video pipeline → sequential; tiny photo sets may use exhaustive
    if source == "video":
        return "sequential"
    if n > 0 and n <= exhaustive_max_images():
        return "exhaustive"
    return "sequential"


def matcher_cli_args(
    matcher: str,
    database_path: str | Path,
    *,
    overlap: int | None = None,
    use_gpu: bool = True,
) -> list[str]:
    """COLMAP argv (without binary) for sequential_matcher or exhaustive_matcher."""
    db = str(database_path)
    ov = int(overlap if overlap is not None else sequential_overlap())
    if matcher == "exhaustive":
        args = ["exhaustive_matcher", "--database_path", db]
    else:
        args = [
            "sequential_matcher",
            "--database_path",
            db,
            "--SequentialMatching.overlap",
            str(ov),
            "--SequentialMatching.quadratic_overlap",
            "1",
        ]
    args.extend(["--SiftMatching.use_gpu", "1" if use_gpu else "0"])
    return args


def feature_extractor_args(
    database_path: str | Path,
    image_path: str | Path,
    *,
    use_gpu: bool = True,
    image_size: int | None = None,
) -> list[str]:
    size = int(image_size if image_size is not None else max_image_size())
    return [
        "feature_extractor",
        "--database_path",
        str(database_path),
        "--image_path",
        str(image_path),
        "--ImageReader.single_camera",
        "1",
        "--SiftExtraction.use_gpu",
        "1" if use_gpu else "0",
        "--SiftExtraction.max_image_size",
        str(size),
    ]


def _strip_glog_prefix(line: str) -> str:
    return _STRIP_GLOG_RE.sub("", line).strip() or line.strip()


def format_colmap_error(
    returncode: int,
    combined: str | None,
    *,
    stage: str = "",
) -> str:
    """Human failure reason — never lead with glog INFO (IYYYYMMDD) dumps."""
    stage_bit = f" ({stage})" if stage else ""
    lines = [ln.strip() for ln in (combined or "").splitlines() if ln.strip()]

    err_lines: list[str] = []
    warn_lines: list[str] = []
    other_non_info: list[str] = []
    for ln in lines:
        if _GLOG_INFO_RE.match(ln):
            continue
        if ln.startswith("=") and set(ln) <= {"=", "-", " "}:
            continue
        if _GLOG_ERR_RE.match(ln) or _ERR_KW_RE.search(ln):
            err_lines.append(_strip_glog_prefix(ln))
        elif _GLOG_WARN_RE.match(ln):
            warn_lines.append(_strip_glog_prefix(ln))
        else:
            other_non_info.append(_strip_glog_prefix(ln))

    chosen = err_lines[-3:] or warn_lines[-2:] or other_non_info[-2:]
    if chosen:
        snippet = " | ".join(chosen)
        if len(snippet) > 280:
            snippet = snippet[:277] + "..."
        return f"COLMAP exit {returncode}{stage_bit}: {snippet}"

    # Pure INFO tail (typical GPU crash mid matching) — honest, not a log dump
    hint = ""
    blob = (combined or "").lower()
    if "match" in blob or stage in ("exhaustive_matcher", "sequential_matcher", "matcher"):
        hint = (
            " — matcher прерван (часто GPU OOM на exhaustive). "
            "Для видео используется sequential; повторите Build 3D."
        )
    elif returncode in (15, -15, 0xC0000005, 3221225477):
        hint = " — процесс COLMAP аварийно завершён"
    return f"COLMAP exit {returncode}{stage_bit}{hint}"


def count_registered_images(sparse_dir: Path) -> int:
    """Count registered images in a COLMAP model (TXT preferred, else BIN size heuristic)."""
    txt = sparse_dir / "images.txt"
    if txt.is_file():
        n = 0
        try:
            lines = txt.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return 0
        i = 0
        while i < len(lines):
            ln = lines[i].strip()
            if not ln or ln.startswith("#"):
                i += 1
                continue
            # IMAGE line then POINTS2D line
            n += 1
            i += 2
        return n
    bin_path = sparse_dir / "images.bin"
    if bin_path.is_file():
        # Rough lower bound: empty header is tiny; each image ≫ 100 bytes
        sz = bin_path.stat().st_size
        if sz < 64:
            return 0
        return max(1, sz // 200)
    return 0


def registration_failure_message(n_frames: int, n_registered: int) -> str | None:
    """RU hint when mapper registered too few images; None if OK."""
    need = max(MIN_REGISTERED_ABS, int(n_frames * MIN_REGISTERED_RATIO))
    if n_registered >= need:
        return None
    if n_registered < MIN_REGISTERED_ABS:
        return (
            "Недостаточно перекрытий/текстуры: попробуйте другой сегмент "
            "или более медленный пролёт"
        )
    return (
        f"Зарегистрировано мало кадров ({n_registered}/{n_frames}). "
        "Недостаточно перекрытий/текстуры: попробуйте другой сегмент "
        "или более медленный пролёт"
    )


# Coarse progress within phase=colmap (export_poses starts ~0.65).
_STAGE_PROGRESS: dict[str, float] = {
    "plan": 0.18,
    "feature_extractor": 0.25,
    "sequential_matcher": 0.35,
    "exhaustive_matcher": 0.35,
    "mapper": 0.45,
    "model_converter": 0.60,
}


def colmap_stage_progress(stage: str) -> float:
    """Progress fraction for a named COLMAP stage (not a fake percentage clock)."""
    return float(_STAGE_PROGRESS.get((stage or "").strip().lower(), 0.35))


def sparse_mapper_snapshot(sparse_dir: Path | None) -> dict[str, Any]:
    """Count sparse/N models and latest write — for live mapper progress (no fake %)."""
    out: dict[str, Any] = {
        "model_count": 0,
        "last_model": None,
        "last_write_age_sec": None,
        "last_write_ts": None,
    }
    if sparse_dir is None or not sparse_dir.is_dir():
        return out
    models: list[tuple[str, float]] = []
    try:
        children = list(sparse_dir.iterdir())
    except OSError:
        return out
    for child in children:
        if not child.is_dir():
            continue
        name = child.name
        if not name.isdigit():
            continue
        latest = 0.0
        for marker in (
            "points3D.bin",
            "points3D.txt",
            "images.bin",
            "images.txt",
            "cameras.bin",
            "cameras.txt",
            "project.ini",
        ):
            p = child / marker
            if p.is_file():
                try:
                    latest = max(latest, p.stat().st_mtime)
                except OSError:
                    continue
        if latest <= 0:
            try:
                latest = child.stat().st_mtime
            except OSError:
                latest = 0.0
        models.append((name, latest))
    if not models:
        return out
    models.sort(key=lambda x: int(x[0]))
    # Tie-break equal mtimes by higher model index (Windows often shares 1s resolution)
    newest_name, newest_ts = max(models, key=lambda x: (x[1], int(x[0])))
    out["model_count"] = len(models)
    out["last_model"] = newest_name
    if newest_ts > 0:
        out["last_write_ts"] = newest_ts
        out["last_write_age_sec"] = max(0, int(time.time() - newest_ts))
    return out


def format_colmap_stage_message(
    stage: str,
    *,
    n_frames: int = 0,
    matcher: str = "",
    snap: dict[str, Any] | None = None,
) -> str:
    """Human-readable stage line for SSE / ops modal (RU-friendly, stage id kept)."""
    st = (stage or "").strip().lower()
    if st == "plan":
        m = matcher or "sequential"
        return f"COLMAP plan (matcher={m}, frames={int(n_frames)})"
    if st == "feature_extractor":
        return "feature_extractor…"
    if st in ("sequential_matcher", "exhaustive_matcher"):
        return f"{st}…"
    if st == "mapper":
        if snap and int(snap.get("model_count") or 0) > 0:
            age = snap.get("last_write_age_sec")
            last = snap.get("last_model")
            age_bit = f" · last write {age}s ago" if age is not None else ""
            last_bit = f" · sparse/{last}" if last is not None else ""
            return f"mapper · models={snap['model_count']}{last_bit}{age_bit}"
        return "mapper…"
    if st == "model_converter":
        return "model_converter…"
    return st or "COLMAP…"


def mapper_progress_from_snapshot(snap: dict[str, Any] | None) -> float:
    """Bump progress slightly as sparse models appear (capped below export_poses)."""
    base = colmap_stage_progress("mapper")
    n = int((snap or {}).get("model_count") or 0)
    # Each new model +0.02, hard cap 0.58 (export_poses uses 0.65)
    return min(0.58, base + 0.02 * max(0, n))
