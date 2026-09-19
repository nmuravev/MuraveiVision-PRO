"""MuraveiVision PRO Backend — FastAPI entrypoint."""
import asyncio
import atexit
import logging
import os
import signal
import traceback

# Air-gap: disable Ultralytics AutoUpdate before any ultralytics import.
os.environ.setdefault("ULTRALYTICS_SKIP_REQUIREMENTS_CHECKS", "1")
os.environ.setdefault("YOLO_AUTOINSTALL", "0")
import sys
import site
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import APP_VERSION, BASE_DIR, DIST_DIR
from services.ultralytics_airgap import ensure_ultralytics_airgap

ensure_ultralytics_airgap()

# 1. Air-Gapped: block user site-packages
site.USER_SITE = None
site.ENABLE_USER_SITE = False

# 2. Inject pack-local ffmpeg dirs into PATH (before system PATH)
for _ff_dir in (
    BASE_DIR / "assets" / "ffmpeg",
    BASE_DIR / "sidecars" / "ffmpeg",
    BASE_DIR / "assets",
):
    if _ff_dir.is_dir():
        os.environ["PATH"] = str(_ff_dir) + os.pathsep + os.environ.get("PATH", "")


REQUIRED_DIRS = ("cache", "logs", "archive", "reports", "assets")


def ensure_runtime_dirs() -> None:
    for name in REQUIRED_DIRS:
        d = BASE_DIR / name
        d.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "archive" / "crops").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "archive" / "recordings").mkdir(parents=True, exist_ok=True)


# P0: Module-level _run_hook for non-fatal startup hooks (A3: unit-testable)
import inspect

logger = logging.getLogger(__name__)
failed_components = []


async def _run_hook(name: str, fn):
    """Run a startup/shutdown hook (sync or async) inside try/except.

    fn: callable that returns result (sync or coroutine).
    Called INSIDE try to catch ValueError from config parsing.
    """
    try:
        result = fn()  # sync-вызов ВНУТРИ try!
        if inspect.isawaitable(result):
            result = await result  # async-хуки тоже поддерживаются
        logger.info(f"[lifespan] {name}: OK")
        return result
    except Exception as exc:
        logger.error(f"[lifespan] {name} FAILED (non-fatal): {exc}")
        logger.debug(traceback.format_exc())
        failed_components.append(name)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # P0: Single-instance guard (R3: check before any startup)
    from services.single_instance import get_guard

    guard = get_guard()
    if not guard.acquire():
        logger.error("[single_instance] Another backend already running. Exiting.")
        sys.exit(1)

    ensure_runtime_dirs()
    # P2-15: Defer ffmpeg resolution to background — does not block app startup.
    # File-existence checks are fast, but logging/print output should not
    # delay YOLO engine loading or network workers that operators depend on.
    async def _resolve_ffmpeg_bg() -> None:
        try:
            from services.ffmpeg_util import resolve_ffmpeg, resolve_ffprobe

            _fp, _fs = resolve_ffmpeg()
            _pp, _ps = resolve_ffprobe()
            print(f"[ffmpeg] path={_fp} source={_fs}")
            print(f"[ffprobe] path={_pp} source={_ps}")
        except Exception as _ff_exc:  # noqa: BLE001
            print(f"[ffmpeg] resolve failed: {_ff_exc}")

    asyncio.create_task(_resolve_ffmpeg_bg())
    from services.db import init_db, migrate_db

    init_db()
    migrate_db()
    # P0-8: Auto-migrate legacy pickle catalog to msgpack (one-time)
    try:
        from scripts.migrate_catalog_v1_to_v2 import run_migration as migrate_catalog
        migrate_catalog(force=False)
    except Exception as _cat_exc:
        print(f"[CATALOG] Migration skip: {_cat_exc}")
    from services.trash import purge_old_trash, trash_root

    trash_root()
    # Optional 30-day trash cleanup (disable with MURAVEI_TRASH_PURGE=0)
    if os.environ.get("MURAVEI_TRASH_PURGE", "1") != "0":
        purged = purge_old_trash()
        if purged:
            print(f"[SYSTEM] Trash auto-purge: removed {purged} item(s)")

    from services.yolo_engine import get_yolo_engine

    from services import runtime_log

    class _RuntimeLogHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                msg = self.format(record)
                lvl = record.levelname.lower()
                if lvl == "warning":
                    lvl = "warn"
                elif lvl not in ("error", "warn", "info", "debug"):
                    lvl = "info"
                runtime_log.write(lvl, "uvicorn", msg)
            except Exception:  # noqa: BLE001
                pass

    rt_handler = _RuntimeLogHandler()
    rt_handler.setFormatter(logging.Formatter("%(message)s"))
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(logger_name)
        lg.addHandler(rt_handler)

    runtime_log.info("system", f"BASE_DIR={BASE_DIR}")
    runtime_log.info("system", f"dist exists={DIST_DIR.is_dir()}")

    engine = get_yolo_engine()
    await engine.start_worker()
    runtime_log.info("yolo", f"mode={engine.mode} model={engine.model_name}")
    print(f"[SYSTEM] BASE_DIR: {BASE_DIR}")
    print(f"[SYSTEM] YOLO mode={engine.mode} model={engine.model_name}")
    print(f"[SYSTEM] Static dist: {DIST_DIR} exists={DIST_DIR.is_dir()}")
    print("[SYSTEM] MuraveiVision PRO Backend starting...")
    from services.network_sync import start_network_worker, stop_network_worker
    from services import network_beacon as nb
    from services.ollama_proxy import startup_reconnect
    from services.accelerator import log_profile_once
    from services.hardware_detect import log_detect_once

    # P6.1: Sync session tokens from DB to in-memory cache
    await _run_hook("session_sync", lambda: (
        __import__('api.auth', fromlist=['_sync_db_to_memory'])._sync_db_to_memory(),
        __import__('api.auth', fromlist=['cleanup_expired_sessions']).cleanup_expired_sessions()
    )[0])

    # P0: Все хуки через _run_hook(lambda: ...) — вызов ВНУТРИ try
    await _run_hook("network_worker", lambda: start_network_worker())
    await _run_hook("beacon", lambda: nb.start_beacon_if_enabled())
    await _run_hook("ollama_reconnect", lambda: startup_reconnect())
    await _run_hook("hardware_detect", lambda: (log_profile_once(), log_detect_once()))
    if failed_components:
        logger.warning(f"[lifespan] {len(failed_components)} components failed: {failed_components}")
    yield
    print("[SYSTEM] Backend stopping...")
    # P0-2: Cancel any remaining background tasks
    try:
        from api.network import _background_tasks
        for task in list(_background_tasks):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        _background_tasks.clear()
    except Exception as _bg_exc:
        print(f"[SYSTEM] Background task cleanup: {_bg_exc}")
    # R4.2: Shutdown hooks через _run_hook (симметрия: падение не роняет процесс)
    await _run_hook("stop_beacon", lambda: nb.stop_beacon())
    await _run_hook("stop_network_worker", lambda: stop_network_worker())


# === B7.1: Log PID at startup for debug ===
import os
logger.info(f"[SYSTEM] Backend PID: {os.getpid()}")


app = FastAPI(
    title="MuraveiVision PRO API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(StarletteHTTPException)
async def catalog_http_exception_handler(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    from services.error_catalog import build_error_payload

    payload = build_error_payload(exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(RequestValidationError)
async def catalog_validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    from services.error_catalog import build_error_payload

    payload = build_error_payload(422, exc.errors())
    return JSONResponse(status_code=422, content=payload)


@app.exception_handler(Exception)
async def catalog_unhandled_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    import logging

    from services.error_catalog import build_error_payload

    logging.getLogger("uvicorn.error").error("Unhandled error: %s", exc, exc_info=True)
    payload = build_error_payload(500, str(exc) or "Internal server error")
    # Prefer stable catalog title for operators; keep exception text in message via detail.
    return JSONResponse(status_code=500, content=payload)


# Local-only CORS (dev Vite + same-origin production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# KEEP: session trace — do not remove without explicit user order
from services.trace_middleware import SessionTraceMiddleware  # noqa: E402

app.add_middleware(SessionTraceMiddleware)


@app.get("/api/health")
async def health_check():
    yolo_mode = "unknown"
    yolo_model = ""
    try:
        from services.yolo_engine import get_yolo_engine

        eng = get_yolo_engine()
        yolo_mode = eng.mode
        yolo_model = eng.model_name or ""
    except Exception:  # noqa: BLE001
        yolo_mode = "offline"
    return {
        "status": "ok",
        "version": APP_VERSION,
        "base_dir": str(BASE_DIR),
        "static": DIST_DIR.is_dir(),
        "mode": "production" if DIST_DIR.is_dir() else "api-only",
        "yolo_mode": yolo_mode,
        "yolo_model": yolo_model,
        "db": str((BASE_DIR / "muravei.db").exists()),
    }


# Routers registered after definition to avoid circular imports
def _register_routers() -> None:
    from api.media import router as media_router
    from api.detect import router as detect_router
    from api.auth import router as auth_router
    from api.detections import router as detections_router
    from api.ai import router as ai_router
    from api.train import router as train_router
    from api.scan import router as scan_router
    from api.geo import router as geo_router
    from api.support import router as support_router
    from api.rec import router as rec_router
    from api.reports import router as reports_router
    from api.export import router as export_router
    from api.models import router as models_router
    from api.system import router as system_router
    from api.network import router as network_router
    from api.ws_chat import router as ws_chat_router
    from api.queue import router as queue_router
    from api.live import router as live_router
    from api.classes_api import router as classes_router
    from api.recon import router as recon_router
    from api.hud import router as hud_router
    from api.debug import router as debug_router
    from api.active_learning import router as active_learning_router
    from api.events import router as events_router
    from api.seg import router as seg_router
    from api.change_detection import router as change_detection_router
    from api.map import router as map_router

    app.include_router(media_router)
    app.include_router(detect_router)
    app.include_router(auth_router)
    app.include_router(detections_router)
    app.include_router(ai_router)
    app.include_router(train_router)
    app.include_router(scan_router)
    app.include_router(geo_router)
    app.include_router(support_router)
    app.include_router(rec_router)
    app.include_router(reports_router)
    app.include_router(export_router)
    app.include_router(models_router)
    app.include_router(system_router)
    app.include_router(network_router)
    app.include_router(ws_chat_router)
    app.include_router(queue_router)
    app.include_router(live_router)
    app.include_router(classes_router)
    app.include_router(recon_router)
    app.include_router(hud_router)
    app.include_router(debug_router)
    app.include_router(active_learning_router)
    app.include_router(events_router)
    app.include_router(seg_router)
    app.include_router(change_detection_router)
    app.include_router(map_router)


_register_routers()


def _mount_static() -> None:
    """Serve Vite build from dist/ when present (portable / production)."""
    if not DIST_DIR.is_dir() or not (DIST_DIR / "index.html").is_file():
        print("[SYSTEM] dist/ missing — API-only (use Vite :3000 in development)")
        return

    assets = DIST_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/")
    async def spa_index():
        return FileResponse(DIST_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Never shadow API / WS
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Not found")
        candidate = DIST_DIR / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST_DIR / "index.html")

    print(f"[SYSTEM] Serving UI from {DIST_DIR}")


_mount_static()


if __name__ == "__main__":
    import atexit
    import uvicorn

    reload = os.environ.get("MURAVEI_RELOAD", "0") == "1"
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=reload,
        log_level="info",
    )


# P0: Process cleanup on exit (R3: SIGINT re-raise for graceful Ctrl+C)
def _cleanup_on_exit():
    """Cleanup child processes on exit."""
    try:
        import psutil
        parent = psutil.Process(os.getpid())
        for child in parent.children(recursive=True):
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
    except (ImportError, Exception):
        pass


def _sigint_handler(signum, frame):
    """R3: Cleanup + re-raise KeyboardInterrupt for uvicorn graceful shutdown."""
    _cleanup_on_exit()
    signal.default_int_handler(signum, frame)  # re-raise → uvicorn graceful Ctrl+C


signal.signal(signal.SIGINT, _sigint_handler)
atexit.register(_cleanup_on_exit)
