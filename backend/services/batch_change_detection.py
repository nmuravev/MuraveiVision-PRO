"""P3.15.5: Batch Change Detection — subsample auto_sync pairs + analyze_pair.

One global in-memory job (like batch_segmentation). Does not write SQLite,
does not touch yolo_engine / trainer / seg / SAM.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Literal

_lock = threading.Lock()
_abort = threading.Event()
_thread: threading.Thread | None = None

_state: dict[str, Any] = {
    "task_id": None,
    "status": "idle",  # idle|running|done|error|aborted
    "progress": 0.0,
    "processed": 0,
    "sample_total": 0,
    "message": "",
    "error": None,
    "video_before": None,
    "video_after": None,
    "source": "auto",
    "pair_stride": 1,
    "max_pairs": 50,
    "use_image_fallback": False,
    "tolerance_m": 10.0,
    "moved_m": 3.0,
    "time_window_sec": 0.5,
    "sync_method": None,
    "pair_count_total": 0,
    "results": [],
    "aggregate": None,
}


def _snapshot(*, include_results: bool = False) -> dict[str, Any]:
    with _lock:
        out = {
            "task_id": _state["task_id"],
            "status": _state["status"],
            "progress": float(_state["progress"]),
            "processed": int(_state["processed"]),
            "sample_total": int(_state["sample_total"]),
            "message": _state["message"],
            "error": _state["error"],
            "video_before": _state["video_before"],
            "video_after": _state["video_after"],
            "source": _state["source"],
            "pair_stride": int(_state["pair_stride"]),
            "max_pairs": int(_state["max_pairs"]),
            "use_image_fallback": bool(_state["use_image_fallback"]),
            "sync_method": _state["sync_method"],
            "pair_count_total": int(_state["pair_count_total"] or 0),
        }
        terminal = _state["status"] in ("done", "aborted", "error")
        if include_results or terminal:
            out["results"] = list(_state["results"])
            out["aggregate"] = _state["aggregate"]
        else:
            out["results"] = None
            out["aggregate"] = None
        return out


def status(task_id: str | None = None) -> dict[str, Any]:
    with _lock:
        current = _state["task_id"]
        terminal = _state["status"] in ("done", "aborted", "error")
    if task_id is not None and current is not None and task_id != current:
        raise KeyError(f"unknown task_id: {task_id}")
    if task_id is not None and current is None:
        raise KeyError(f"unknown task_id: {task_id}")
    return _snapshot(include_results=terminal)


def _set(**kwargs: Any) -> None:
    with _lock:
        for k, v in kwargs.items():
            if k in _state:
                _state[k] = v


def _strip_heatmap(result: dict[str, Any]) -> dict[str, Any]:
    """Drop heavy ORB heatmap from stored pair results."""
    out = dict(result)
    image_diff = out.get("image_diff")
    if isinstance(image_diff, dict):
        trimmed = {k: v for k, v in image_diff.items() if k != "heatmap_b64"}
        out["image_diff"] = trimmed or None
    return out


def build_aggregate(results: list[dict[str, Any]], *, sync_method: str | None) -> dict[str, Any]:
    """Sum per-pair summaries + unique detection-id sets for new/removed/moved."""
    sum_new = 0
    sum_removed = 0
    sum_moved = 0
    sum_stable = 0
    sum_matched = 0
    unique_new: set[str] = set()
    unique_removed: set[str] = set()
    unique_moved: set[str] = set()  # before_id|after_id key

    for row in results:
        summary = row.get("summary") or {}
        sum_new += int(summary.get("new") or 0)
        sum_removed += int(summary.get("removed") or 0)
        sum_moved += int(summary.get("moved") or 0)
        sum_stable += int(summary.get("stable") or 0)
        sum_matched += int(summary.get("matched") or 0)
        for item in row.get("new") or []:
            did = item.get("id")
            if did:
                unique_new.add(str(did))
        for item in row.get("removed") or []:
            did = item.get("id")
            if did:
                unique_removed.add(str(did))
        for m in row.get("matches") or []:
            if m.get("status") != "moved":
                continue
            key = f"{m.get('before_id')}|{m.get('after_id')}"
            unique_moved.add(key)

    return {
        "pair_count": len(results),
        "sync_method": sync_method,
        "sum_new": sum_new,
        "sum_removed": sum_removed,
        "sum_moved": sum_moved,
        "sum_stable": sum_stable,
        "sum_matched": sum_matched,
        "unique_new": len(unique_new),
        "unique_removed": len(unique_removed),
        "unique_moved": len(unique_moved),
    }


def _pair_row(
    pair: dict[str, Any],
    analyzed: dict[str, Any],
) -> dict[str, Any]:
    summary = analyzed.get("summary") or {}
    return {
        "time_before": float(pair.get("time_before") or 0),
        "time_after": float(pair.get("time_after") or 0),
        "method": analyzed.get("method") or "none",
        "aligned": bool(analyzed.get("aligned")),
        "message": analyzed.get("message"),
        "summary": summary,
        "matches": list(analyzed.get("matches") or []),
        "new": list(analyzed.get("new") or []),
        "removed": list(analyzed.get("removed") or []),
        "image_diff": analyzed.get("image_diff"),
    }


def _run(
    task_id: str,
    video_before: str,
    video_after: str,
    source: str,
    pair_stride: int,
    max_pairs: int,
    use_image_fallback: bool,
    tolerance_m: float,
    moved_m: float,
    time_window_sec: float,
    sync_tolerance_m: float,
) -> None:
    from services.change_detection import analyze_pair
    from services.time_sync import auto_sync

    results: list[dict[str, Any]] = []
    processed = 0
    sync_method: str | None = None

    try:
        _set(message="Синхронизация пар…", progress=0.0)
        sync = auto_sync(
            video_before,
            video_after,
            source=source,  # type: ignore[arg-type]
            tolerance_m=sync_tolerance_m,
        )
        sync_method = str(sync.get("method_used") or "none")
        pairs = list(sync.get("pairs") or [])
        pair_count_total = int(sync.get("pair_count_total") or len(pairs))
        _set(sync_method=sync_method, pair_count_total=pair_count_total)

        if not pairs:
            msg = sync.get("message") or "Нет пар синхронизации"
            agg = build_aggregate([], sync_method=sync_method)
            _set(
                status="done",
                progress=1.0,
                processed=0,
                sample_total=0,
                results=[],
                aggregate=agg,
                message=str(msg),
                error=None,
            )
            return

        stride = max(1, int(pair_stride))
        work = pairs[::stride][: max(1, int(max_pairs))]
        sample_total = len(work)
        _set(
            sample_total=sample_total,
            message=f"Пар {sample_total}/{pair_count_total} (stride={stride})",
        )

        for pair in work:
            if _abort.is_set():
                agg = build_aggregate(results, sync_method=sync_method)
                _set(
                    status="aborted",
                    message="Пакетный CD прерван",
                    results=list(results),
                    aggregate=agg,
                    processed=processed,
                    progress=processed / sample_total if sample_total else 0.0,
                )
                return

            analyzed = analyze_pair(
                video_before=video_before,
                video_after=video_after,
                time_before=float(pair.get("time_before") or 0),
                time_after=float(pair.get("time_after") or 0),
                tolerance_m=tolerance_m,
                moved_m=moved_m,
                time_window_sec=time_window_sec,
                use_gps=True,
                use_image_fallback=use_image_fallback,
            )
            row = _pair_row(pair, _strip_heatmap(analyzed))
            results.append(row)
            processed += 1
            summary = row.get("summary") or {}
            _set(
                processed=processed,
                progress=min(1.0, processed / sample_total if sample_total else 0.0),
                results=list(results),
                message=(
                    f"Пара {processed}/{sample_total}: "
                    f"+{summary.get('new', 0)}/"
                    f"-{summary.get('removed', 0)}/"
                    f"↔{summary.get('moved', 0)}"
                ),
            )

        agg = build_aggregate(results, sync_method=sync_method)
        _set(
            status="done",
            progress=1.0,
            processed=processed,
            results=list(results),
            aggregate=agg,
            message=(
                f"Готово: {processed} пар · "
                f"уник. +{agg['unique_new']}/-{agg['unique_removed']}/↔{agg['unique_moved']}"
            ),
            error=None,
        )
    except Exception as exc:  # noqa: BLE001
        agg = build_aggregate(results, sync_method=sync_method)
        _set(
            status="error",
            error=str(exc),
            message=f"Ошибка пакетного CD: {exc}",
            results=list(results),
            aggregate=agg,
            processed=processed,
        )


def start(
    *,
    video_before: str,
    video_after: str,
    source: Literal["auto", "tracks", "detections"] = "auto",
    pair_stride: int = 1,
    max_pairs: int = 50,
    use_image_fallback: bool = False,
    tolerance_m: float = 10.0,
    moved_m: float = 3.0,
    time_window_sec: float = 0.5,
    sync_tolerance_m: float = 15.0,
) -> dict[str, Any]:
    global _thread
    if not video_before or not video_after:
        raise ValueError("video_before and video_after required")

    stride = max(1, min(50, int(pair_stride)))
    capped = max(1, min(200, int(max_pairs)))

    with _lock:
        if _state["status"] == "running" or (_thread is not None and _thread.is_alive()):
            raise RuntimeError("Пакетный Change Detection уже выполняется")
        task_id = uuid.uuid4().hex[:12]
        _abort.clear()
        # KEEP: session trace — do not remove without explicit user order
        from services.trace_middleware import pipeline_trace

        pipeline_trace(
            "cd",
            f"batch_cd start task={task_id} before={video_before} after={video_after}",
            trace_id=task_id,
        )
        _state.update(
            {
                "task_id": task_id,
                "status": "running",
                "progress": 0.0,
                "processed": 0,
                "sample_total": 0,
                "message": "Старт пакетного CD…",
                "error": None,
                "video_before": str(video_before),
                "video_after": str(video_after),
                "source": source,
                "pair_stride": stride,
                "max_pairs": capped,
                "use_image_fallback": bool(use_image_fallback),
                "tolerance_m": float(tolerance_m),
                "moved_m": float(moved_m),
                "time_window_sec": float(time_window_sec),
                "sync_method": None,
                "pair_count_total": 0,
                "results": [],
                "aggregate": None,
            }
        )
        thr = threading.Thread(
            target=_run,
            args=(
                task_id,
                video_before,
                video_after,
                source,
                stride,
                capped,
                bool(use_image_fallback),
                float(tolerance_m),
                float(moved_m),
                float(time_window_sec),
                float(sync_tolerance_m),
            ),
            name=f"batch-cd-{task_id}",
            daemon=True,
        )
        _thread = thr
        thr.start()

    return _snapshot(include_results=False)


def abort(task_id: str) -> dict[str, Any]:
    with _lock:
        if _state["task_id"] != task_id:
            raise KeyError(f"unknown task_id: {task_id}")
        if _state["status"] != "running":
            return _snapshot(include_results=True)
    _abort.set()
    deadline = time.time() + 5.0
    while time.time() < deadline:
        with _lock:
            if _state["status"] != "running":
                break
        time.sleep(0.05)
    return status(task_id)
