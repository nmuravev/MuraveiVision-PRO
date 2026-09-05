"""3D reconstruction API — COLMAP sidecar + SSE progress + gsplat train presets."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from services import recon_scanner, recon_train
from services.security import require_role
from services.train_presets import presets_for_client

router = APIRouter(tags=["recon"])


class ReconStartBody(BaseModel):
    video_path: str = Field(..., min_length=1)
    t_start: float | None = Field(default=None, ge=0)
    t_end: float | None = Field(default=None, ge=0)
    fps_sample: float = Field(default=1.0, ge=0.1, le=5.0)


class ManifestPatchBody(BaseModel):
    scale_m_per_unit: float | None = None
    scale_reference: dict[str, Any] | None = None
    rotation_x: float | None = None


class TrainStartBody(BaseModel):
    job_id: str = Field(..., min_length=8, max_length=32)
    preset: str = Field(..., min_length=1, max_length=32)


@router.get("/api/recon/status")
async def recon_status(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, Any]:
    return recon_scanner.status()


@router.post("/api/recon/start")
async def recon_start(
    body: ReconStartBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    if recon_train.status().get("status") == "training":
        raise HTTPException(status_code=409, detail="Дождитесь завершения обучения 3D")
    try:
        return recon_scanner.start(
            video_path=body.video_path,
            t_start=body.t_start,
            t_end=body.t_end,
            fps_sample=body.fps_sample,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/recon/stop")
async def recon_stop(_user: dict[str, Any] = Depends(require_role("operator"))) -> dict[str, Any]:
    return recon_scanner.stop()


@router.get("/api/recon/stream")
async def recon_stream(_user: dict[str, Any] = Depends(require_role("operator"))) -> StreamingResponse:
    async def gen():
        idx = 0
        last_status_push = 0.0
        yield f"data: {json.dumps({'type': 'status', **recon_scanner.status()}, ensure_ascii=False)}\n\n"
        while True:
            events, idx = recon_scanner.drain_events(idx)
            for ev in events:
                yield f"data: {json.dumps({'type': 'progress', **ev}, ensure_ascii=False)}\n\n"
                if ev.get("status") in ("done", "colmap_done", "error", "idle"):
                    return
            st = recon_scanner.status()
            if st.get("status") in ("done", "colmap_done", "error", "idle") and not events:
                yield f"data: {json.dumps({'type': 'status', **st}, ensure_ascii=False)}\n\n"
                return
            # Heartbeat while running so long mapper stages refresh FE without new events
            now = time.monotonic()
            if st.get("status") == "running" and (now - last_status_push) >= 2.0 and not events:
                yield f"data: {json.dumps({'type': 'status', **st}, ensure_ascii=False)}\n\n"
                last_status_push = now
            await asyncio.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/api/recon/manifest")
async def recon_manifest(
    video_path: str = Query(...),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        man = recon_scanner.get_manifest(video_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not man:
        return {"manifest": None, "colmap_available": recon_scanner.colmap_available()}
    return {
        "manifest": man,
        "colmap_available": recon_scanner.colmap_available(),
        "colmap_path": recon_scanner.colmap_path(),
    }


@router.patch("/api/recon/manifest/{job_id}")
async def recon_manifest_patch(
    job_id: str,
    body: ManifestPatchBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    patch = body.model_dump(exclude_unset=True)
    try:
        man = recon_scanner.update_manifest(job_id, patch)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"manifest": man}


@router.get("/api/recon/poses")
async def recon_poses(
    video_path: str = Query(...),
    time_sec: float = Query(..., ge=0),
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        payload = recon_scanner.get_poses_at_time(video_path, time_sec)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not payload:
        raise HTTPException(status_code=404, detail="Нет camera poses для этого видео")
    return payload


@router.get("/api/recon/asset/{job_id}/{name}")
async def recon_asset(
    job_id: str,
    name: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
):
    try:
        path = recon_scanner.asset_path(job_id, name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    media = {
        ".ply": "application/octet-stream",
        ".splat": "application/octet-stream",
        ".json": "application/json",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".obj": "text/plain",
        ".mtl": "text/plain",
    }
    return FileResponse(path, media_type=media.get(path.suffix.lower(), "application/octet-stream"))


@router.get("/api/recon/export/{job_id}/{kind}")
async def recon_export_artifact(
    job_id: str,
    kind: str,
    _user: dict[str, Any] = Depends(require_role("operator")),
):
    """Download a single artifact file, or ZIP for mesh (obj+mtl+textures)."""
    import io
    import zipfile

    from services.job_ids import sanitize_job_id
    from services.alicevision_pipeline import normalize_artifacts
    from services.security import BASE_DIR

    job_id = sanitize_job_id(job_id)
    job_dir = BASE_DIR / "archive" / "recon" / job_id
    man_path = job_dir / "manifest.json"
    if not man_path.is_file():
        raise HTTPException(status_code=404, detail="job not found")
    try:
        man = json.loads(man_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="bad manifest") from exc
    man = normalize_artifacts(man)
    arts = man.get("artifacts") or {}
    entry = arts.get(kind) if isinstance(arts, dict) else None
    if not isinstance(entry, dict) or not entry.get("file"):
        # Fallbacks
        if kind == "splat" and (job_dir / "model.ply").is_file():
            entry = {"file": "model.ply"}
        elif kind == "dense" and (job_dir / "dense_point_cloud.ply").is_file():
            entry = {"file": "dense_point_cloud.ply"}
        elif kind == "mesh" and (job_dir / "textured_mesh.obj").is_file():
            entry = {"file": "textured_mesh.obj"}
        elif kind == "sparse":
            entry = {"file": man.get("sparse_file") or "sparse_points.json"}
        else:
            raise HTTPException(status_code=404, detail=f"artifact {kind} missing")

    fname = str(entry["file"])
    if kind == "mesh" and fname.lower().endswith(".obj"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            obj = job_dir / fname
            if not obj.is_file():
                raise HTTPException(status_code=404, detail=fname)
            zf.write(obj, obj.name)
            mtl = obj.with_suffix(".mtl")
            if mtl.is_file():
                zf.write(mtl, mtl.name)
            for tex in sorted(job_dir.iterdir()):
                if not tex.is_file():
                    continue
                low = tex.name.lower()
                if low.endswith((".png", ".jpg", ".jpeg", ".tif")) and not low.startswith("000"):
                    zf.write(tex, tex.name)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{job_id}_{kind}.zip"'},
        )

    try:
        path = recon_scanner.asset_path(job_id, fname)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=path.name,
    )


@router.get("/api/recon/train/presets")
async def recon_train_presets(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return {"presets": presets_for_client(), "colmap_running": recon_scanner.status().get("status") == "running"}


@router.get("/api/recon/train/status")
async def recon_train_status(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return recon_train.status()


@router.post("/api/recon/train/start")
async def recon_train_start(
    body: TrainStartBody,
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    try:
        return recon_train.start(body.job_id, body.preset)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/api/recon/train/stop")
async def recon_train_stop(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> dict[str, Any]:
    return recon_train.stop()


@router.get("/api/recon/train/stream")
async def recon_train_stream(
    _user: dict[str, Any] = Depends(require_role("operator")),
) -> StreamingResponse:
    async def gen():
        idx = 0
        yield f"data: {json.dumps({'type': 'status', **recon_train.status()}, ensure_ascii=False)}\n\n"
        while True:
            events, idx = recon_train.drain_events(idx)
            for ev in events:
                yield f"data: {json.dumps({'type': 'progress', **ev}, ensure_ascii=False)}\n\n"
                if ev.get("status") in ("done", "error", "idle"):
                    return
            st = recon_train.status()
            if st.get("status") in ("done", "error", "idle") and not events:
                yield f"data: {json.dumps({'type': 'status', **st}, ensure_ascii=False)}\n\n"
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream")
