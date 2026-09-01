# 3D Reconstruction (COLMAP + gsplat)

Visual-only photogrammetry for archive MP4 **without GPS**. Designed for EW/jammed environments where SRT telemetry is unavailable.

## Requirements

| Component | Where |
|-----------|--------|
| Python 3.12.10 | `muravei_env\Scripts\python.exe` only |
| COLMAP | Optional sidecar via `COLMAP_ROOT` |
| gsplat (train) | Prebuilt wheel on build machine + NVIDIA CUDA |
| ffmpeg/ffprobe | `assets/ffmpeg.exe` or PATH |

## Quick start

1. Stage COLMAP sidecar (once):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stage_colmap_sidecar.ps1
$env:COLMAP_ROOT = "D:\LLM\MuraveiVision-PRO\sidecars\colmap"
Test-Path "$env:COLMAP_ROOT\colmap.exe"   # True, or COLMAP.bat
& "$env:COLMAP_ROOT\colmap.exe" -h         # quick CLI check (or COLMAP.bat help)
```

2. Start backend:

```powershell
npm run backend
```

3. In UI: open MP4 → **Flight3D** → **Построить 3D** (segment ≤120 s from playhead).

4. After `colmap_done`: toggle **Сцена**, optional **Масштаб** (2 clicks + metres).

5. **Inspector** → **Показать в 3D** on a detection → raycast marker (or «Пересечение не найдено»).

## API

| Method | Path |
|--------|------|
| POST | `/api/recon/start` `{ video_path, t_start?, t_end?, fps_sample }` |
| GET | `/api/recon/status` |
| GET | `/api/recon/stream` (SSE, Authorization header) |
| GET | `/api/recon/manifest?video_path=` |
| PATCH | `/api/recon/manifest/{job_id}` scale / horizon |
| GET | `/api/recon/poses?video_path=&time_sec=` |
| GET | `/api/recon/asset/{job_id}/{name}` |

## Artifacts

```
archive/recon/{job_id}/
├── frames/
├── colmap/sparse/0/
├── camera_poses.json    # R, t, intrinsics, image_size per frame
├── sparse_points.json   # COLMAP point cloud preview
└── manifest.json
```

## Raycast math

- Ray from **drone intrinsics** `(u,v)` pixels — not Three.js NDC.
- `dir_world = R^T @ normalize([(u-cx)/fx, (v-cy)/fy, 1])`
- Intersection: sparse point cloud fallback; splat depth-pick when `.splat`/`.ply` artifact exists.
- Flight3D «Сцена»: `preview.ply` / sparse JSON → `THREE.Points`; `model.ply` / `.splat` → `@mkkellogg/gaussian-splats-3d` DropInViewer.
- `scale_direction` in manifest → local azimuth (North alignment).

## Smoke test

```powershell
npm run smoke:recon
```

## gsplat train (optional)

1. Install **prebuilt** wheel into `muravei_env` (no MSVC on field PC):

```powershell
.\muravei_env\Scripts\pip.exe install --no-cache-dir gsplat
```

2. Optional: vendor nerfstudio `examples/simple_trainer.py` under `sidecars/gsplat_examples/` for full 3DGS. Without it, after COLMAP the job exports `preview.ply` (colored COLMAP points) via `backend/scripts/gsplat_train_job.py`.

3. Env knobs: `GSPLAT_MAX_STEPS` (default 500), `GSPLAT_TIMEOUT` (default 3600).

When `manifest.artifact` is set (`model.ply` / `preview.ply`), Flight3D shows splat-ready status; raycast prefers sparse cloud until splat depth-pick is wired (C.5).
