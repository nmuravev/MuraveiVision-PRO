"""MuraveiVision PRO Backend — FastAPI entrypoint."""
import os
import sys
import site
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# 1. Air-Gapped: block user site-packages
site.USER_SITE = None
site.ENABLE_USER_SITE = False

# 2. BASE_DIR for .exe and .py
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

# 3. Inject ffmpeg into PATH when present
ffmpeg_path = BASE_DIR / "assets"
if ffmpeg_path.exists():
    os.environ["PATH"] = str(ffmpeg_path) + os.pathsep + os.environ.get("PATH", "")

DIST_DIR = BASE_DIR / "dist"


def safe_path_resolve(path: str | Path) -> Path:
    try:
        return Path(path).resolve()
    except (FileNotFoundError, OSError, NotADirectoryError):
        return Path(path).absolute()


REQUIRED_DIRS = ("cache", "logs", "archive", "reports", "assets")


def ensure_runtime_dirs() -> None:
    for name in REQUIRED_DIRS:
        d = BASE_DIR / name
        d.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "archive" / "crops").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "archive" / "recordings").mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_runtime_dirs()
    from services.db import init_db

    init_db()
    from services.trash import purge_old_trash, trash_root

    trash_root()
    # Optional 30-day trash cleanup (disable with MURAVEI_TRASH_PURGE=0)
    import os

    if os.environ.get("MURAVEI_TRASH_PURGE", "1") != "0":
        purged = purge_old_trash()
        if purged:
            print(f"[SYSTEM] Trash auto-purge: removed {purged} item(s)")

    from services.yolo_engine import get_yolo_engine

    from services import runtime_log
    import logging

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
    yield
    print("[SYSTEM] Backend stopping...")


app = FastAPI(
    title="MuraveiVision PRO API",
    version="1.0.0",
    lifespan=lifespan,
)

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
        "version": "1.0.0",
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
    from api.queue import router as queue_router
    from api.live import router as live_router
    from api.classes_api import router as classes_router
    from api.recon import router as recon_router
    from api.debug import router as debug_router
    from api.active_learning import router as active_learning_router

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
    app.include_router(queue_router)
    app.include_router(live_router)
    app.include_router(classes_router)
    app.include_router(recon_router)
    app.include_router(debug_router)
    app.include_router(active_learning_router)


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
    import uvicorn

    reload = os.environ.get("MURAVEI_RELOAD", "0") == "1"
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=reload,
        log_level="info",
    )
